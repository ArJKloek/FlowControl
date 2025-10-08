
# ASYNC COMMAND TESTING - Add this to your application to test async performance

def test_async_commands(poller, test_address=3):
    """Test async commands with timing debug output."""
    
    print("\n🚀 STARTING ASYNC COMMAND PERFORMANCE TEST")
    print("=" * 60)
    
    # Test 1: Async setpoint flow changes
    print("\n📋 Test 1: Async Setpoint Flow Changes")
    test_values = [10.0, 25.0, 50.0, 75.0, 100.0]
    
    start_time = time.time()
    for i, value in enumerate(test_values):
        print(f"\n--- Command {i+1}/5: Setting flow to {value} ---")
        poller.request_async_setpoint_flow(test_address, value, timeout=0.3)
        time.sleep(0.05)  # Small delay between commands to see sequencing
    
    # Wait for all commands to complete
    time.sleep(2.0)
    total_time = time.time() - start_time
    print(f"\n✅ Test 1 Complete: 5 setpoint changes in {total_time:.2f}s")
    print(f"   Average per command: {total_time/5*1000:.1f}ms")
    
    # Test 2: Async setpoint percentage changes  
    print("\n📋 Test 2: Async Setpoint Percentage Changes")
    test_percentages = [10, 30, 50, 80, 100]
    
    start_time = time.time()
    for i, percent in enumerate(test_percentages):
        print(f"\n--- Command {i+1}/5: Setting {percent}% ---")
        poller.request_async_setpoint_pct(test_address, percent, timeout=0.3)
        time.sleep(0.05)
    
    time.sleep(2.0)
    total_time = time.time() - start_time
    print(f"\n✅ Test 2 Complete: 5 percentage changes in {total_time:.2f}s")
    print(f"   Average per command: {total_time/5*1000:.1f}ms")
    
    # Test 3: Async fluid changes
    print("\n📋 Test 3: Async Fluid Changes")
    test_fluids = [0, 1, 2, 3, 0]  # Cycle through fluid indexes
    
    start_time = time.time()
    for i, fluid_idx in enumerate(test_fluids):
        print(f"\n--- Command {i+1}/5: Setting fluid {fluid_idx} ---")
        poller.request_async_fluid_change(test_address, fluid_idx, timeout=0.5)
        time.sleep(0.05)
    
    time.sleep(3.0)  # Fluid changes might take longer
    total_time = time.time() - start_time
    print(f"\n✅ Test 3 Complete: 5 fluid changes in {total_time:.2f}s")
    print(f"   Average per command: {total_time/5*1000:.1f}ms")
    
    # Test 4: Async reads
    print("\n📋 Test 4: Async Parameter Reads")
    
    start_time = time.time()
    for i in range(5):
        print(f"\n--- Read {i+1}/5: Reading fMeasure ---")
        poller.request_async_read(test_address, 205, timeout=0.2)  # FMEASURE_DDE
        time.sleep(0.02)
    
    time.sleep(1.0)
    total_time = time.time() - start_time
    print(f"\n✅ Test 4 Complete: 5 reads in {total_time:.2f}s")
    print(f"   Average per command: {total_time/5*1000:.1f}ms")
    
    # Test 5: Mixed command sequence
    print("\n📋 Test 5: Mixed Async Commands")
    
    start_time = time.time()
    commands = [
        ("setpoint_flow", 45.0),
        ("read", 205),
        ("setpoint_pct", 60),
        ("read", 205),
        ("fluid", 1),
        ("read", 205),
        ("setpoint_flow", 80.0),
        ("read", 205)
    ]
    
    for i, (cmd_type, value) in enumerate(commands):
        print(f"\n--- Mixed Command {i+1}/8: {cmd_type} {value} ---")
        if cmd_type == "setpoint_flow":
            poller.request_async_setpoint_flow(test_address, value, timeout=0.3)
        elif cmd_type == "setpoint_pct":
            poller.request_async_setpoint_pct(test_address, value, timeout=0.3)
        elif cmd_type == "fluid":
            poller.request_async_fluid_change(test_address, value, timeout=0.5)
        elif cmd_type == "read":
            poller.request_async_read(test_address, value, timeout=0.2)
        time.sleep(0.02)
    
    time.sleep(3.0)
    total_time = time.time() - start_time
    print(f"\n✅ Test 5 Complete: 8 mixed commands in {total_time:.2f}s")
    print(f"   Average per command: {total_time/8*1000:.1f}ms")
    
    print("\n🏆 ASYNC PERFORMANCE TEST COMPLETE!")
    print("Check the debug output above for detailed timing information.")

# Example usage:
# test_async_commands(your_poller, test_address=3)
