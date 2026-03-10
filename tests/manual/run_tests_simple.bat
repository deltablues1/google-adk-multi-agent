@echo off
echo ===================================================================
echo   AUTOMATED TEST SUITE - SIMPLE VERSION
echo ===================================================================
echo.
echo Starting tests with real data...
echo User: Tomislav Golic (tgolic555@gmail.com)
echo.
echo This will take approximately 5-10 minutes.
echo Press Ctrl+C to cancel.
echo.
pause

python test_runner_simple.py

echo.
echo ===================================================================
echo   TESTS COMPLETED
echo ===================================================================
echo.
pause
