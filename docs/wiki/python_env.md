


🧠 Using the simnibs_python interpreter
Task	Command / Description
Check location	which simnibs_python (mac/Linux) or where simnibs_python (Windows)
List installed packages	simnibs_python -m pip list
Install new package	simnibs_python -m pip install <package>
Upgrade existing package	simnibs_python -m pip install --upgrade <package>
Update pip itself	simnibs_python -m pip install --upgrade pip setuptools wheel
Create a separate virtual environment (recommended)	simnibs_python -m venv ~/simnibs_venv → source ~/simnibs_venv/bin/activate

💡 Tips

simnibs_python is a self-contained interpreter — you can manage it like any Python installation.

Use -m pip to safely install or list packages within it.

For experimental installs, use a virtual environment to keep the core SimNIBS setup stable.
