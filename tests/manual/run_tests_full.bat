@echo off
echo ===================================================================
echo   AUTOMATED TEST SUITE - FULL VERSION
echo ===================================================================
echo.
echo Starting comprehensive tests with real data...
echo User: Tomislav Golic (tgolic555@gmail.com)
echo.
echo This will take approximately 15-30 minutes.
echo Results will be saved to test_results_*.log and *.json files.
echo.
echo Press Ctrl+C to cancel.
echo.
pause

python test_runner.py

echo.
echo ===================================================================
echo   TESTS COMPLETED
echo ===================================================================
echo.
echo Check the following files for detailed results:
echo   - test_results_*.log (detailed log)
echo   - test_results_*.json (JSON summary)
echo.
pause
