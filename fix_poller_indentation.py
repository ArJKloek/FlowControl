#!/usr/bin/env python3
"""
Fix indentation issues in poller.py.
This script removes the broken command processing section and replaces it with a clean version.
"""
import os

def fix_poller_indentation():
    """Fix the indentation issues in poller.py by replacing the broken section."""
    
    poller_path = r"c:\Users\klar\OneDrive - Hanzehogeschool Groningen\Documenten\GitHub\FlowControl\backend\poller.py"
    
    print("🔧 FIXING POLLER.PY INDENTATION")
    print(f"Working on: {poller_path}")
    
    # Read the entire file
    try:
        with open(poller_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # Try with different encoding
        with open(poller_path, 'r', encoding='cp1252') as f:
            content = f.read()
    
    print(f"Original file size: {len(content)} characters")
    
    # The problem is in the command processing section around lines 175-420
    # Let's find the start and end markers
    
    # Find the start of the problematic section (the else: block after queue processing)
    start_marker = "                else:\n                    try:\n                        # Use shared instrument with proper locking for USB device coordination"
    
    # Find the end marker (before the crash prevention section)
    end_marker = "                    except Exception as cmd_error:\n                        # Handle command processing errors gracefully"
    
    start_pos = content.find(start_marker)
    end_pos = content.find(end_marker)
    
    if start_pos == -1 or end_pos == -1:
        print("❌ Could not find the problematic section markers")
        return False
    
    print(f"Found problematic section: {start_pos} to {end_pos}")
    
    # Create the fixed command processing section
    fixed_section = '''                else:
                    try:
                        # Use shared instrument with proper locking for USB device coordination
                        inst = self.manager.get_shared_instrument(self.port, address)
                        
                        if kind == "fluid":
                            old_rt = getattr(inst.master, "response_timeout", 0.5)
                            try:
                                # fluid switches can take longer; give the write a bit more time
                                inst.master.response_timeout = max(old_rt, 0.8)
                                # Enhanced safe conversion for fluid index
                                try:
                                    safe_arg = int(arg) if arg not in (None, "", " ") else 0
                                except (ValueError, TypeError):
                                    safe_arg = 0
                                res = inst.writeParameter(FIDX_DDE, safe_arg, verify=True, debug=True)
                            finally:
                                inst.master.response_timeout = old_rt
                            
                            # Normalize immediate result
                            ok_immediate = (
                                res is True or res == PP_STATUS_OK or res == 0 or
                                (isinstance(res, dict) and res.get("status", 1) in (0, PP_STATUS_OK))
                            )
                            # If it timed out (25) or wasn't clearly OK, do a read-back verify.
                            applied = ok_immediate
                            if not ok_immediate or res == PP_STATUS_TIMEOUT_ANSWER:    
                                deadline = time.monotonic() + 5.0
                                time.sleep(0.2)  # tiny settle
                                while time.monotonic() < deadline:
                                    try:
                                        idx_now = inst.readParameter(FIDX_DDE)
                                        name_now = inst.readParameter(FNAME_DDE)
                                        if idx_now == (int(arg) if arg is not None else 0) and name_now:
                                            applied = True
                                            break
                                    except Exception:
                                        pass
                                    time.sleep(0.15)
                            if applied:
                                # optional telemetry
                                self.telemetry.emit({
                                    "ts": time.time(), "port": self.port, "address": address,
                                    "kind": "fluid_change", "name": "fluid_index", "value": int(arg) if arg is not None else 0
                                })
                            else:
                                name = pp_status_codes.get(res, str(res))
                                self.error.emit(f"{self.port}/{address}: fluid change to {arg} not confirmed (res={res} {name})")
                                
                        elif kind == "fset_flow":
                            # Get device identification to check if gas compensation should be applied
                            device_type = None
                            gas_factor = 1.0
                            device_setpoint = float(arg)  # Send user value directly to device (no compensation on setpoint)
                            
                            # Check if this is a DMFC device for telemetry logging
                            if hasattr(self, 'manager') and self.manager:
                                try:
                                    # Get device type from manager's node cache
                                    device_type = self.manager.get_device_type(self.port, address)
                                    
                                    # Get gas factor for telemetry purposes only (not for setpoint compensation)
                                    if device_type == "DMFC":
                                        serial_nr = self.manager.get_serial_number(self.port, address)
                                        gas_factor = self.manager.get_gas_factor(self.port, address, serial_nr)
                                        # NOTE: We do NOT compensate the setpoint - device handles this internally
                                except Exception:
                                    # If anything fails, use original value
                                    pass
                            
                            # slightly higher timeout for writes (still much lower than 0.5s default)
                            old_rt = getattr(inst.master, "response_timeout", 0.5)
                            try:
                                inst.master.response_timeout = max(old_rt, 0.20)
                                res = inst.writeParameter(FSETPOINT_DDE, device_setpoint)
                            finally:
                                inst.master.response_timeout = old_rt

                            # normalize "immediate OK"
                            ok_immediate = (
                                (res is True) or
                                (res == PP_STATUS_OK) or
                                (isinstance(res, dict) and res.get("status") == PP_STATUS_OK)
                            )

                            if ok_immediate:
                                # great — nothing else to do
                                pass
                            elif res == PP_STATUS_TIMEOUT_ANSWER:
                                # timed out waiting for ACK; either verify or (optionally) ignore
                                if IGNORE_TIMEOUT_ON_SETPOINT:
                                    # do nothing: treat as success
                                    pass
                                else:
                                    # verify by reading back
                                    try:
                                        rb = inst.readParameter(FSETPOINT_DDE)
                                    except Exception:
                                        rb = None
                                    ok = False
                                    if isinstance(rb, (int, float)):
                                        tol = 1e-3 * max(1.0, abs(float(device_setpoint)))
                                        ok = abs(float(rb) - float(device_setpoint)) <= tol
                                    if not ok:
                                        name = pp_status_codes.get(res, str(res))
                                        self.error.emit(f"{self.port}/{address}: setpoint write timeout; verify failed (res={res} {name}, rb={rb})")
                            else:
                                # some other status → report
                                name = pp_status_codes.get(res, str(res))
                                self.error.emit(f"{self.port}/{address}: setpoint write status {res} ({name})")
                            
                            # Emit setpoint telemetry
                            if device_type == "DMFC" and gas_factor != 1.0:
                                # For DMFC devices: emit both the compensated and raw setpoint values
                                compensated_setpoint = device_setpoint * gas_factor if gas_factor != 0 else device_setpoint
                                self.telemetry.emit({
                                    "ts": time.time(), "port": self.port, "address": address,
                                    "kind": "setpoint", "name": "fSetpoint", "value": round(compensated_setpoint, 1)
                                })
                                # Raw device setpoint (what we actually send to device) - raw telemetry
                                self.telemetry.emit({
                                    "ts": time.time(), "port": self.port, "address": address,
                                    "kind": "setpoint", "name": "fSetpoint_raw", "value": round(device_setpoint, 1)
                                })
                            else:
                                # Non-DMFC or no compensation: emit normal setpoint
                                self.telemetry.emit({
                                    "ts": time.time(), "port": self.port, "address": address,
                                    "kind": "setpoint", "name": "fSetpoint", "value": round(float(arg), 1)
                                })
                
                        elif kind == "set_pct":
                            # slightly higher timeout for writes (still much lower than 0.5s default)
                            old_rt = getattr(inst.master, "response_timeout", 0.5)
                            try:
                                inst.master.response_timeout = max(old_rt, 0.20)
                                # Enhanced safe conversion for setpoint
                                try:
                                    safe_arg = int(arg) if arg not in (None, "", " ") else 0
                                except (ValueError, TypeError):
                                    safe_arg = 0
                                res = inst.writeParameter(SETPOINT_DDE, safe_arg)
                            finally:
                                inst.master.response_timeout = old_rt

                            # normalize "immediate OK"
                            ok_immediate = (
                                (res is True) or
                                (res == PP_STATUS_OK) or
                                (isinstance(res, dict) and res.get("status") == PP_STATUS_OK)
                            )

                            if ok_immediate:
                                # great — nothing else to do                        
                                pass
                            elif res == PP_STATUS_TIMEOUT_ANSWER:
                                # timed out waiting for ACK; either verify or (optionally) ignore
                                if IGNORE_TIMEOUT_ON_SETPOINT:
                                    # do nothing: treat as success
                                    pass
                                else:
                                    # verify by reading back
                                    try:
                                        rb = inst.readParameter(SETPOINT_DDE)
                                    except Exception:
                                        rb = None
                                    ok = False
                                    if isinstance(rb, (int, int)):
                                        tol = 1e-3 * max(1.0, abs(int(arg) if arg is not None else 0))
                                        ok = abs((int(rb) if rb is not None else 0) - (float(arg) if arg is not None else 0.0)) <= tol
                                    if not ok:
                                        name = pp_status_codes.get(res, str(res))
                                        self.error.emit(f"{self.port}/{address}: setpoint write timeout; verify failed (res={res} {name}, rb={rb})")
                            else:
                                # some other status → report
                                name = pp_status_codes.get(res, str(res))
                                self.error.emit(f"{self.port}/{address}: setpoint write status {res} ({name})")
                            
                            self.telemetry.emit({
                                "ts": time.time(), "port": self.port, "address": address,
                                "kind": "setpoint", "name": "Setpoint_pct", "value": int(arg) if arg is not None else 0
                            })
                
                        elif kind == "set_usertag":
                            # slightly higher timeout for writes (still much lower than 0.5s default)
                            old_rt = getattr(inst.master, "response_timeout", 0.5)
                            try:
                                inst.master.response_timeout = max(old_rt, 0.20)
                                res = inst.writeParameter(USERTAG_DDE, str(arg))
                            finally:
                                inst.master.response_timeout = old_rt

                            # normalize "immediate OK"
                            ok_immediate = (
                                (res is True) or
                                (res == PP_STATUS_OK) or
                                (isinstance(res, dict) and res.get("status") == PP_STATUS_OK)
                            )

                            if ok_immediate:
                                # great — nothing else to do                        
                                pass
                            elif res == PP_STATUS_TIMEOUT_ANSWER:
                                # timed out waiting for ACK; either verify or (optionally) ignore
                                if IGNORE_TIMEOUT_ON_SETPOINT:
                                    # do nothing: treat as success
                                    pass
                                else:
                                    # verify by reading back
                                    try:
                                        rb = inst.readParameter(USERTAG_DDE)
                                    except Exception:
                                        rb = None
                                    
                                    ok = rb == str(arg)
                                    if not ok:
                                        name = pp_status_codes.get(
                                        res if isinstance(res, int) else (res.get("status") if isinstance(res, dict) else None),
                                        str(res)
                                        )
                                        self.error.emit(
                                        f"{self.port}/{address}: usertag write timeout; verify failed (res={res} {name}, rb={arg!r})"
                                        )
                            else:
                                # some other status → report
                                name = pp_status_codes.get(res, str(res))
                                self.error.emit(f"{self.port}/{address}: setpoint write status {res} ({name})")
                            
                            self.telemetry.emit({
                                "ts": time.time(), "port": self.port, "address": address,
                                "kind": "set", "name": "Usertag", "value": str(arg)
                            })
                    
                    '''
    
    # Add the exception handler back
    fixed_section += '''                    except Exception as cmd_error:
                        # Handle command processing errors gracefully
                        print(f"Command processing error for {self.port} address {address}: {cmd_error}")
                        self.error.emit(f"Command processing failed for {self.port}/{address}: {cmd_error}")'''
    
    # Replace the broken section
    before = content[:start_pos]
    after = content[end_pos + len(end_marker):]
    
    new_content = before + fixed_section + after
    
    # Write the fixed file
    with open(poller_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✅ Fixed file written: {len(new_content)} characters")
    print("🎯 Key fixes applied:")
    print("   • Fixed indentation in command processing section")
    print("   • Properly nested try/except blocks")
    print("   • Aligned elif statements correctly")
    print("   • Added missing exception handler")
    
    return True

if __name__ == "__main__":
    success = fix_poller_indentation()
    if success:
        print("\n✅ POLLER.PY INDENTATION FIXED!")
        print("The application should now start without syntax errors.")
    else:
        print("\n❌ FAILED TO FIX POLLER.PY")
        print("Manual intervention required.")