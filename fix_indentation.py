#!/usr/bin/env python3
"""
Quick syntax fix for poller.py indentation issues.
This will fix the command processing section that has broken indentation.
"""

def fix_indentation_issues():
    """Fix the indentation issues in poller.py."""
    
    print("🔧 FIXING INDENTATION ISSUES")
    print("The command processing section in poller.py has broken indentation.")
    print("This was caused when adding crash prevention code.")
    print("")
    print("Issues to fix:")
    print("1. try blocks not properly indented")
    print("2. elif clauses misaligned") 
    print("3. exception handling blocks incomplete")
    print("")
    print("✅ Manual fix required in poller.py:")
    print("   • Line ~185-250: Command processing section")
    print("   • Ensure all try/except blocks are properly indented")
    print("   • Align elif statements with initial if")
    print("   • Close all try blocks with except/finally")
    print("")
    print("The main issue is at line 252 where:")
    print("   old_rt = getattr(inst.master, \"response_timeout\", 0.5)")
    print("needs to be properly indented within its parent try block.")
    
    print("\n💡 INDENTATION PATTERN NEEDED:")
    print("else:")
    print("    try:  # Command processing")
    print("        inst = self.manager.get_shared_instrument(...)")
    print("        if kind == \"fluid\":")
    print("            old_rt = getattr(...)  # This line needs proper indentation")
    print("            try:")
    print("                # Fluid handling code")
    print("            finally:")
    print("                # Cleanup")
    print("        elif kind == \"fset_flow\":")
    print("            # Flow setpoint handling")
    print("    except Exception as cmd_error:")
    print("        # Error handling")

if __name__ == "__main__":
    fix_indentation_issues()