"""
TradeMind AI — Silent launcher.
Using .pyw extension runs with pythonw.exe which suppresses the console window.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
exec(open(os.path.join(os.path.dirname(__file__), "main.py")).read())
