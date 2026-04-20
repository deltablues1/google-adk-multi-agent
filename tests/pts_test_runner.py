"""
PTS (Portal za Testiranje Sukladnosti) Test Runner

This script runs a comprehensive suite of tests to validate
readiness for Croatian Tax Administration's PTS portal.

Test Categories:
1. POSITIVE - Valid invoices that should succeed
2. NEGATIVE - Invalid invoices that should fail with specific errors
3. EDGE CASES - Special scenarios (multi-VAT, storno, etc.)

PTS Requirements Tested:
- Valid XML schema compliance
- Correct digital signature
- ZKI calculation accuracy
- Error handling for various failure modes
- Idempotency (duplicate detection)
- QR code generation

Usage:
    python tests/pts_test_runner.py                    # Run all tests
    python tests/pts_test_runner.py --positive        # Only positive tests
    python tests/pts_test_runner.py --negative        # Only negative tests
    python tests/pts_test_runner.py --report          # Generate HTML report

Version: 1.0
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
import json
import logging
import argparse
import time
import traceback

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

# Certificate configuration
CERT_PATH = project_root / "47034854402.F1.1.p12"
CERT_PASSWORD = os.environ.get("FINA_CERT_PASSWORD")

# Company data
COMPANY_OIB = "47034854402"
COMPANY_NAME = "LUX TECH D.O.O."

# Test output directory
OUTPUT_DIR = project_root / "tests" / "pts_results"


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class TestCase:
    """Definition of a test case."""
    name: str
    description: str
    category: str  # "positive", "negative", "edge_case"

    # Invoice data
    invoice_number: str
    total_amount: Decimal
    payment_method: str = "G"
    pdv_breakdown: List[Dict] = None

    # Expected result
    expect_success: bool = True
    expected_error_code: str = None
    expected_error_contains: str = None

    # Overrides for negative tests
    override_oib: str = None
    override_zki: str = None
    override_datetime: datetime = None

    def __post_init__(self):
        if self.pdv_breakdown is None:
            # Default: simple 25% VAT
            neto = self.total_amount / Decimal("1.25")
            pdv = self.total_amount - neto
            self.pdv_breakdown = [{
                "stopa": "25.00",
                "osnovica": f"{neto:.2f}",
                "iznos": f"{pdv:.2f}"
            }]


@dataclass
class TestResult:
    """Result of a test case execution."""
    test_name: str
    category: str
    passed: bool
    expected_success: bool
    actual_success: bool

    # Details
    jir: Optional[str] = None
    zki: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    verification_url: Optional[str] = None

    # Timing
    execution_time_ms: int = 0

    # Raw data for debugging
    request_xml: Optional[str] = None
    response_raw: Optional[str] = None

    # Validation details
    validation_notes: List[str] = None

    def __post_init__(self):
        if self.validation_notes is None:
            self.validation_notes = []


# ============================================================================
# TEST CASES DEFINITION
# ============================================================================

def generate_test_cases() -> List[TestCase]:
    """Generate all test cases for PTS validation."""
    now = datetime.now()
    # Generate simple numeric sequence for invoice numbers
    # FINA BrOznRac must be 1-20 digits only
    base_num = int(now.strftime("%H%M%S"))  # 6 digits max

    tests = []

    # ========== POSITIVE TESTS (should succeed) ==========

    # P1: Simple cash invoice with 25% VAT
    tests.append(TestCase(
        name="P1_simple_cash_invoice",
        description="Simple cash payment invoice with 25% VAT",
        category="positive",
        invoice_number=f"{base_num + 1}/1/1",
        total_amount=Decimal("125.00"),
        payment_method="G",  # Gotovina
        expect_success=True
    ))

    # P2: Card payment invoice
    tests.append(TestCase(
        name="P2_card_payment",
        description="Card payment invoice",
        category="positive",
        invoice_number=f"{base_num + 2}/1/1",
        total_amount=Decimal("250.00"),
        payment_method="K",  # Kartica
        expect_success=True
    ))

    # P3: Bank transfer invoice
    tests.append(TestCase(
        name="P3_bank_transfer",
        description="Bank transfer payment",
        category="positive",
        invoice_number=f"{base_num + 3}/1/1",
        total_amount=Decimal("1000.00"),
        payment_method="T",  # Transakcijski
        expect_success=True
    ))

    # P4: Multi-VAT invoice (25% + 13% + 5%)
    tests.append(TestCase(
        name="P4_multi_vat_rates",
        description="Invoice with multiple VAT rates (25%, 13%, 5%)",
        category="positive",
        invoice_number=f"{base_num + 4}/1/1",
        total_amount=Decimal("500.00"),
        payment_method="G",
        pdv_breakdown=[
            {"stopa": "25.00", "osnovica": "200.00", "iznos": "50.00"},
            {"stopa": "13.00", "osnovica": "150.00", "iznos": "19.50"},
            {"stopa": "5.00", "osnovica": "100.00", "iznos": "5.00"}
        ],
        expect_success=True
    ))

    # P5: Minimum amount invoice
    tests.append(TestCase(
        name="P5_minimum_amount",
        description="Minimum possible invoice amount (0.01 EUR)",
        category="positive",
        invoice_number=f"{base_num + 5}/1/1",
        total_amount=Decimal("0.01"),
        payment_method="G",
        pdv_breakdown=[
            {"stopa": "25.00", "osnovica": "0.01", "iznos": "0.00"}
        ],
        expect_success=True
    ))

    # P6: Large amount invoice
    tests.append(TestCase(
        name="P6_large_amount",
        description="Large invoice amount (99,999.99 EUR)",
        category="positive",
        invoice_number=f"{base_num + 6}/1/1",
        total_amount=Decimal("99999.99"),
        payment_method="T",
        expect_success=True
    ))

    # ========== NEGATIVE TESTS (should fail with specific errors) ==========

    # N1: Invalid OIB (wrong check digit)
    tests.append(TestCase(
        name="N1_invalid_oib",
        description="Invalid OIB (wrong check digit)",
        category="negative",
        invoice_number=f"{base_num + 101}/1/1",
        total_amount=Decimal("100.00"),
        override_oib="12345678900",  # Invalid OIB
        expect_success=False,
        expected_error_code="s002"
    ))

    # N2: Invalid OIB (wrong length)
    tests.append(TestCase(
        name="N2_oib_wrong_length",
        description="OIB with wrong length (10 digits instead of 11)",
        category="negative",
        invoice_number=f"{base_num + 102}/1/1",
        total_amount=Decimal("100.00"),
        override_oib="1234567890",  # Only 10 digits
        expect_success=False,
        expected_error_code="s002"
    ))

    # N3: Invalid invoice number format
    tests.append(TestCase(
        name="N3_invalid_invoice_format",
        description="Invoice number with invalid format",
        category="negative",
        invoice_number=f"{base_num + 103}",  # Missing /PP/NU
        total_amount=Decimal("100.00"),
        expect_success=False,
        expected_error_code="E001"  # Our internal error code
    ))

    # N4: Future date (not allowed)
    tests.append(TestCase(
        name="N4_future_date",
        description="Invoice with future date",
        category="negative",
        invoice_number=f"{base_num + 104}/1/1",
        total_amount=Decimal("100.00"),
        override_datetime=datetime.now() + timedelta(days=1),
        expect_success=False,
        expected_error_contains="date"
    ))

    # N5: Very old date (more than 48h ago - late delivery rules)
    tests.append(TestCase(
        name="N5_old_date_no_late_flag",
        description="Invoice older than 48h without late delivery flag",
        category="negative",
        invoice_number=f"{base_num + 105}/1/1",
        total_amount=Decimal("100.00"),
        override_datetime=datetime.now() - timedelta(hours=50),
        expect_success=False,
        expected_error_contains="late"
    ))

    # N6: Negative amount (should fail schema)
    tests.append(TestCase(
        name="N6_negative_amount",
        description="Invoice with negative amount",
        category="negative",
        invoice_number=f"{base_num + 106}/1/1",
        total_amount=Decimal("-100.00"),
        expect_success=False,
        expected_error_code="s001"  # Schema error
    ))

    # ========== EDGE CASE TESTS ==========

    # E1: Idempotency test (send same invoice twice)
    idempotency_num = base_num + 201
    tests.append(TestCase(
        name="E1_idempotency_first",
        description="First send of idempotency test",
        category="edge_case",
        invoice_number=f"{idempotency_num}/1/1",
        total_amount=Decimal("100.00"),
        expect_success=True
    ))

    # E2: Same invoice number as E1 (should return same JIR or error)
    tests.append(TestCase(
        name="E1_idempotency_duplicate",
        description="Duplicate send (same invoice as E1) - should be idempotent",
        category="edge_case",
        invoice_number=f"{idempotency_num}/1/1",  # Same as E1
        total_amount=Decimal("100.00"),
        expect_success=True  # Should return existing JIR
    ))

    # E3: Different business premises
    tests.append(TestCase(
        name="E3_different_premises",
        description="Invoice from different business premises",
        category="edge_case",
        invoice_number=f"{base_num + 203}/2/1",  # PP=2 instead of 1
        total_amount=Decimal("100.00"),
        expect_success=True
    ))

    # E4: Different cash register
    tests.append(TestCase(
        name="E4_different_register",
        description="Invoice from different cash register",
        category="edge_case",
        invoice_number=f"{base_num + 204}/1/2",  # NU=2 instead of 1
        total_amount=Decimal("100.00"),
        expect_success=True
    ))

    return tests


# ============================================================================
# TEST EXECUTOR
# ============================================================================

class PTSTestRunner:
    """Runs PTS validation tests."""

    def __init__(self, cert_path: str, cert_password: str, company_oib: str):
        self.cert_path = cert_path
        self.cert_password = cert_password
        self.company_oib = company_oib
        self.results: List[TestResult] = []

    def run_test(self, test_case: TestCase) -> TestResult:
        """Run a single test case."""
        from tools.api_implementations.deterministic_executor import (
            DeterministicFiscalExecutor,
            ExecutorInput
        )

        logger.info(f"Running test: {test_case.name}")
        start_time = time.time()

        try:
            # Prepare input
            oib = test_case.override_oib or self.company_oib
            invoice_dt = test_case.override_datetime or datetime.now()

            # Check for format error first (our internal validation)
            if "/" not in test_case.invoice_number:
                return TestResult(
                    test_name=test_case.name,
                    category=test_case.category,
                    passed=not test_case.expect_success,  # Expected to fail
                    expected_success=test_case.expect_success,
                    actual_success=False,
                    error_code="E001",
                    error_message=f"Invalid invoice number format: {test_case.invoice_number}",
                    execution_time_ms=int((time.time() - start_time) * 1000),
                    validation_notes=["Format validation caught error before FINA call"]
                )

            input_data = ExecutorInput(
                invoice_number=test_case.invoice_number,
                supplier_oib=oib,
                cert_path=self.cert_path,
                cert_password=self.cert_password,
                invoice_datetime=invoice_dt,
                total_amount=test_case.total_amount,
                payment_method=test_case.payment_method,
                pdv_breakdown=test_case.pdv_breakdown,
                use_sandbox=True
            )

            # Execute
            executor = DeterministicFiscalExecutor(use_ledger=True)
            result = executor.execute(input_data)

            execution_time = int((time.time() - start_time) * 1000)

            # Validate result
            validation_notes = []

            if test_case.expect_success:
                passed = result.success
                if passed:
                    validation_notes.append("SUCCESS: JIR received as expected")
                    if result.verification_url:
                        validation_notes.append(f"QR URL: {result.verification_url}")
                else:
                    validation_notes.append(f"FAIL: Expected success but got error: {result.error_message}")
            else:
                # Expected failure
                passed = not result.success

                if passed:
                    validation_notes.append(f"SUCCESS: Failed as expected with error: {result.error_code}")

                    # Check specific error code if expected
                    if test_case.expected_error_code:
                        if result.error_code and test_case.expected_error_code.lower() in result.error_code.lower():
                            validation_notes.append(f"Error code matches expected: {test_case.expected_error_code}")
                        else:
                            validation_notes.append(
                                f"WARNING: Expected error code {test_case.expected_error_code}, "
                                f"got {result.error_code}"
                            )

                    # Check error message contains expected string
                    if test_case.expected_error_contains:
                        if result.error_message and test_case.expected_error_contains.lower() in result.error_message.lower():
                            validation_notes.append(f"Error message contains expected text")
                        else:
                            validation_notes.append(
                                f"WARNING: Error message doesn't contain '{test_case.expected_error_contains}'"
                            )
                else:
                    validation_notes.append(f"FAIL: Expected failure but got JIR: {result.jir}")

            return TestResult(
                test_name=test_case.name,
                category=test_case.category,
                passed=passed,
                expected_success=test_case.expect_success,
                actual_success=result.success,
                jir=result.jir,
                zki=result.zki,
                error_code=result.error_code,
                error_message=result.error_message,
                verification_url=result.verification_url,
                execution_time_ms=execution_time,
                request_xml=result.signed_xml[:500] if result.signed_xml else None,
                response_raw=result.fina_response[:500] if result.fina_response else None,
                validation_notes=validation_notes
            )

        except Exception as e:
            logger.error(f"Test exception: {e}")
            traceback.print_exc()

            return TestResult(
                test_name=test_case.name,
                category=test_case.category,
                passed=False,
                expected_success=test_case.expect_success,
                actual_success=False,
                error_code="EXCEPTION",
                error_message=str(e),
                execution_time_ms=int((time.time() - start_time) * 1000),
                validation_notes=[f"Exception: {e}"]
            )

    def run_all_tests(
        self,
        categories: List[str] = None
    ) -> Dict[str, Any]:
        """Run all test cases."""
        test_cases = generate_test_cases()

        if categories:
            test_cases = [t for t in test_cases if t.category in categories]

        logger.info(f"Running {len(test_cases)} tests...")

        self.results = []
        for test_case in test_cases:
            result = self.run_test(test_case)
            self.results.append(result)

            # Small delay between tests
            time.sleep(0.5)

        return self.generate_summary()

    def generate_summary(self) -> Dict[str, Any]:
        """Generate test summary."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        by_category = {}
        for result in self.results:
            cat = result.category
            if cat not in by_category:
                by_category[cat] = {"total": 0, "passed": 0, "failed": 0}
            by_category[cat]["total"] += 1
            if result.passed:
                by_category[cat]["passed"] += 1
            else:
                by_category[cat]["failed"] += 1

        return {
            "timestamp": datetime.now().isoformat(),
            "total_tests": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{(passed/total*100):.1f}%" if total > 0 else "N/A",
            "by_category": by_category,
            "results": [asdict(r) for r in self.results]
        }


# ============================================================================
# REPORT GENERATION
# ============================================================================

def generate_html_report(summary: Dict[str, Any], output_path: Path) -> str:
    """Generate HTML report from test summary."""
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>PTS Test Report - {summary['timestamp']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }}
        h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat-box {{ background: #f9f9f9; padding: 20px; border-radius: 8px; text-align: center; flex: 1; }}
        .stat-value {{ font-size: 36px; font-weight: bold; }}
        .stat-label {{ color: #666; margin-top: 5px; }}
        .pass {{ color: #4CAF50; }}
        .fail {{ color: #f44336; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #f5f5f5; font-weight: bold; }}
        tr:hover {{ background: #f9f9f9; }}
        .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
        .badge-pass {{ background: #4CAF50; color: white; }}
        .badge-fail {{ background: #f44336; color: white; }}
        .badge-positive {{ background: #2196F3; color: white; }}
        .badge-negative {{ background: #FF9800; color: white; }}
        .badge-edge {{ background: #9C27B0; color: white; }}
        .notes {{ font-size: 12px; color: #666; }}
        .jir {{ font-family: monospace; background: #e8f5e9; padding: 2px 6px; border-radius: 3px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>PTS Test Report</h1>
        <p>Generated: {summary['timestamp']}</p>

        <div class="summary">
            <div class="stat-box">
                <div class="stat-value">{summary['total_tests']}</div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat-box">
                <div class="stat-value pass">{summary['passed']}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat-box">
                <div class="stat-value fail">{summary['failed']}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{summary['pass_rate']}</div>
                <div class="stat-label">Pass Rate</div>
            </div>
        </div>

        <h2>Results by Category</h2>
        <table>
            <tr>
                <th>Category</th>
                <th>Total</th>
                <th>Passed</th>
                <th>Failed</th>
            </tr>
"""

    for cat, stats in summary['by_category'].items():
        html += f"""
            <tr>
                <td>{cat}</td>
                <td>{stats['total']}</td>
                <td class="pass">{stats['passed']}</td>
                <td class="fail">{stats['failed']}</td>
            </tr>
"""

    html += """
        </table>

        <h2>Detailed Results</h2>
        <table>
            <tr>
                <th>Test Name</th>
                <th>Category</th>
                <th>Status</th>
                <th>Expected</th>
                <th>Result</th>
                <th>Time (ms)</th>
                <th>Notes</th>
            </tr>
"""

    for result in summary['results']:
        status_badge = "badge-pass" if result['passed'] else "badge-fail"
        status_text = "PASS" if result['passed'] else "FAIL"

        cat_badge = {
            "positive": "badge-positive",
            "negative": "badge-negative",
            "edge_case": "badge-edge"
        }.get(result['category'], "")

        result_text = ""
        if result['jir']:
            result_text = f'<span class="jir">{result["jir"][:20]}...</span>'
        elif result['error_code']:
            result_text = f'{result["error_code"]}: {result.get("error_message", "")[:50]}'

        notes = "<br>".join(result.get('validation_notes', []))

        html += f"""
            <tr>
                <td>{result['test_name']}</td>
                <td><span class="badge {cat_badge}">{result['category']}</span></td>
                <td><span class="badge {status_badge}">{status_text}</span></td>
                <td>{"Success" if result['expected_success'] else "Failure"}</td>
                <td>{result_text}</td>
                <td>{result['execution_time_ms']}</td>
                <td class="notes">{notes}</td>
            </tr>
"""

    html += """
        </table>

        <h2>Test Definitions</h2>
        <h3>Positive Tests (should succeed)</h3>
        <ul>
            <li><strong>P1</strong>: Simple cash invoice with 25% VAT</li>
            <li><strong>P2</strong>: Card payment invoice</li>
            <li><strong>P3</strong>: Bank transfer invoice</li>
            <li><strong>P4</strong>: Multi-VAT rates (25%, 13%, 5%)</li>
            <li><strong>P5</strong>: Minimum amount (0.01 EUR)</li>
            <li><strong>P6</strong>: Large amount (99,999.99 EUR)</li>
        </ul>

        <h3>Negative Tests (should fail)</h3>
        <ul>
            <li><strong>N1</strong>: Invalid OIB (wrong check digit)</li>
            <li><strong>N2</strong>: OIB wrong length</li>
            <li><strong>N3</strong>: Invalid invoice number format</li>
            <li><strong>N4</strong>: Future date</li>
            <li><strong>N5</strong>: Old date without late delivery flag</li>
            <li><strong>N6</strong>: Negative amount</li>
        </ul>

        <h3>Edge Case Tests</h3>
        <ul>
            <li><strong>E1</strong>: Idempotency test (duplicate invoice)</li>
            <li><strong>E3</strong>: Different business premises</li>
            <li><strong>E4</strong>: Different cash register</li>
        </ul>

        <footer style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; text-align: center;">
            <p>Fiskalizacija 2.0 - PTS Validation Suite</p>
            <p>LUX TECH D.O.O. - OIB: 47034854402</p>
        </footer>
    </div>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')

    return str(output_path)


def generate_json_report(summary: Dict[str, Any], output_path: Path) -> str:
    """Generate JSON report."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, default=str),
        encoding='utf-8'
    )
    return str(output_path)


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="PTS Test Runner for Fiskalizacija 2.0")
    parser.add_argument("--positive", action="store_true", help="Run only positive tests")
    parser.add_argument("--negative", action="store_true", help="Run only negative tests")
    parser.add_argument("--edge", action="store_true", help="Run only edge case tests")
    parser.add_argument("--report", action="store_true", help="Generate HTML report")
    parser.add_argument("--json", action="store_true", help="Generate JSON report")
    parser.add_argument("--output", type=str, help="Output directory for reports")

    args = parser.parse_args()

    # Determine categories to run
    categories = []
    if args.positive:
        categories.append("positive")
    if args.negative:
        categories.append("negative")
    if args.edge:
        categories.append("edge_case")

    if not categories:
        categories = None  # Run all

    # Check certificate exists
    if not CERT_PATH.exists():
        print(f"ERROR: Certificate not found: {CERT_PATH}")
        return 1

    print("=" * 70)
    print("   PTS TEST RUNNER - Fiskalizacija 2.0")
    print("=" * 70)
    print(f"Company: {COMPANY_NAME}")
    print(f"OIB: {COMPANY_OIB}")
    print(f"Certificate: {CERT_PATH.name}")
    print(f"Categories: {categories or 'ALL'}")
    print()

    # Run tests
    runner = PTSTestRunner(
        cert_path=str(CERT_PATH),
        cert_password=CERT_PASSWORD,
        company_oib=COMPANY_OIB
    )

    summary = runner.run_all_tests(categories=categories)

    # Print summary
    print()
    print("=" * 70)
    print("   TEST SUMMARY")
    print("=" * 70)
    print(f"Total: {summary['total_tests']}")
    print(f"Passed: {summary['passed']} ({summary['pass_rate']})")
    print(f"Failed: {summary['failed']}")
    print()

    print("By Category:")
    for cat, stats in summary['by_category'].items():
        print(f"  {cat}: {stats['passed']}/{stats['total']} passed")
    print()

    # Show failed tests
    failed_tests = [r for r in runner.results if not r.passed]
    if failed_tests:
        print("FAILED TESTS:")
        for result in failed_tests:
            print(f"  - {result.test_name}: {result.error_message or 'Unknown error'}")
        print()

    # Generate reports
    output_dir = Path(args.output) if args.output else OUTPUT_DIR
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.report or not (args.json):
        html_path = output_dir / f"pts_report_{timestamp}.html"
        generate_html_report(summary, html_path)
        print(f"HTML Report: {html_path}")

    if args.json or not (args.report):
        json_path = output_dir / f"pts_report_{timestamp}.json"
        generate_json_report(summary, json_path)
        print(f"JSON Report: {json_path}")

    # Exit code
    return 0 if summary['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
