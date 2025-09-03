#!/usr/bin/env python3
"""
Environment diagnostic script for TI-Toolbox Classifier
Helps identify Python environment and package availability issues
"""

import sys
import subprocess
from pathlib import Path

def check_python_info():
    """Check Python interpreter information"""
    print("PYTHON ENVIRONMENT DIAGNOSTICS")
    print("=" * 50)
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version}")
    print(f"Python path: {sys.path[:3]}...")  # First 3 paths
    print()

def check_package(package_name, import_name=None):
    """Check if a package is available"""
    if import_name is None:
        import_name = package_name
    
    try:
        module = __import__(import_name)
        version = getattr(module, '__version__', 'Unknown')
        print(f"✅ {package_name}: {version}")
        return True
    except ImportError as e:
        print(f"❌ {package_name}: NOT AVAILABLE ({e})")
        return False

def check_pip_list():
    """Check what pip thinks is installed"""
    print("\nPIP INSTALLED PACKAGES (relevant ones):")
    print("-" * 40)
    
    try:
        result = subprocess.run([sys.executable, '-m', 'pip', 'list'], 
                              capture_output=True, text=True)
        lines = result.stdout.split('\n')
        
        relevant_packages = ['matplotlib', 'seaborn', 'numpy', 'pandas', 
                           'scipy', 'scikit-learn', 'nibabel', 'joblib']
        
        for line in lines:
            for pkg in relevant_packages:
                if line.lower().startswith(pkg.lower()):
                    print(f"  {line}")
    except Exception as e:
        print(f"Error running pip list: {e}")

def check_import_issues():
    """Test specific imports that might cause issues"""
    print("\nIMPORT TESTS:")
    print("-" * 20)
    
    # Test the problematic imports
    imports_to_test = [
        ('numpy', 'numpy'),
        ('pandas', 'pandas'),
        ('matplotlib', 'matplotlib.pyplot'),
        ('seaborn', 'seaborn'),
        ('sklearn', 'sklearn'),
        ('scipy', 'scipy'),
        ('nibabel', 'nibabel'),
        ('joblib', 'joblib')
    ]
    
    for package_name, import_name in imports_to_test:
        check_package(package_name, import_name)

def test_plotting_imports():
    """Test the specific plotting imports"""
    print("\nPLOTTING MODULE IMPORT TEST:")
    print("-" * 30)
    
    try:
        # Test the exact imports from our plotting module
        import numpy as np
        print("✅ numpy imported successfully")
        
        import pandas as pd
        print("✅ pandas imported successfully")
        
        import matplotlib.pyplot as plt
        print("✅ matplotlib.pyplot imported successfully")
        
        from matplotlib.patches import Rectangle
        print("✅ matplotlib.patches.Rectangle imported successfully")
        
        from sklearn.metrics import roc_curve, auc, confusion_matrix
        print("✅ sklearn.metrics imported successfully")
        
        from scipy import stats
        print("✅ scipy.stats imported successfully")
        
        # Test seaborn specifically
        try:
            import seaborn as sns
            print("✅ seaborn imported successfully")
            print(f"   seaborn version: {sns.__version__}")
            
            # Test seaborn functionality
            plt.style.use('seaborn-v0_8-whitegrid')
            print("✅ seaborn style applied successfully")
            
        except ImportError as e:
            print(f"❌ seaborn import failed: {e}")
        except Exception as e:
            print(f"⚠️  seaborn imported but style failed: {e}")
            
    except Exception as e:
        print(f"❌ Import test failed: {e}")

def suggest_fixes():
    """Suggest potential fixes"""
    print("\nPOTENTIAL FIXES:")
    print("-" * 20)
    print("1. Install seaborn in current environment:")
    print(f"   {sys.executable} -m pip install seaborn>=0.11.0")
    print()
    print("2. If in Docker, make sure you're using the right Python:")
    print("   which python")
    print("   which pip")
    print()
    print("3. Check if you're in a virtual environment:")
    print("   echo $VIRTUAL_ENV")
    print()
    print("4. Try installing all requirements:")
    print(f"   {sys.executable} -m pip install -r requirements.txt")
    print()
    print("5. If still failing, try the fallback plotting (seaborn-free):")
    print("   The plotting module now has fallback support!")

def main():
    """Main diagnostic function"""
    check_python_info()
    check_pip_list()
    check_import_issues()
    test_plotting_imports()
    suggest_fixes()
    
    print("\n" + "=" * 50)
    print("DIAGNOSIS COMPLETE")
    print("=" * 50)

if __name__ == "__main__":
    main()
