"""
Script to fix the corrupted control_dialog.py file
"""

import re

def fix_control_dialog():
    # Read the corrupted file
    with open('backend/control_dialog.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the corrupted _set_spin_if_idle function
    pattern = r'def _set_spin_if_idle\(spin, value, tol=1e-6\):\s*\n.*?def _set_slider_if_idle\(slider, value\):'
    
    # Replacement text
    replacement = '''def _set_spin_if_idle(spin, value, tol=1e-6):
    # don't overwrite while user is editing
    if spin.hasFocus():
        return
    with QSignalBlocker(spin):
        if abs(spin.value() - float(value)) > tol:
            spin.setValue(float(value))


def _set_slider_if_idle(slider, value):'''
    
    # Perform the replacement
    fixed_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    # Check if the replacement was successful
    if fixed_content != content:
        # Write the fixed content
        with open('backend/control_dialog_fixed.py', 'w', encoding='utf-8') as f:
            f.write(fixed_content)
        print("File fixed successfully!")
        return True
    else:
        print("No corruption pattern found or replacement failed")
        return False

if __name__ == "__main__":
    fix_control_dialog()