from ftrace_file import TraceFile
from ftrace_analyzer import Analyzer
import os

# Create a dummy ftrace file for testing
dummy_log = "test_trace.log"
with open(dummy_log, "w") as f:
    f.write("  kworker/u16:0-1234  [000] .... 7541.834000: sched_switch: prev_comm=kworker/u16:0 prev_pid=1234 prev_prio=120 prev_state=S ==> next_comm=swapper/0 next_pid=0 next_prio=120\n")
    f.write("          swapper-0     [000] .... 7541.835000: sched_switch: prev_comm=swapper/0 prev_pid=0 prev_prio=120 prev_state=R ==> next_comm=kube-apiserver next_pid=3711 next_prio=120\n")
    f.write("   kube-apiserver-3711  [000] .... 7541.836000: sched_switch: prev_comm=kube-apiserver prev_pid=3711 prev_prio=120 prev_state=S ==> next_comm=swapper/0 next_pid=0 next_prio=120\n")

try:
    trace = TraceFile(dummy_log)
    analyzer = Analyzer(trace)
    
    print("Testing Analyzer.classify_contexts()...")
    contexts = analyzer.classify_contexts()
    assert 'user_process' in contexts
    assert 'processes' in contexts['user_process']
    print("OK")
    
    print("Testing QueryResult.summary()...")
    query = trace.query()
    res = query.execute()
    summary = res.summary()
    assert 'processes' in summary
    print("OK")
    
    print("Testing QueryBuilder.to_dataframe()...")
    # This might fail if pandas is not installed, which is fine as it's optional
    df = query.to_dataframe()
    print(f"to_dataframe returned: {type(df)}")
    
finally:
    if os.path.exists(dummy_log):
        os.remove(dummy_log)
    if os.path.exists(dummy_log + ".index"):
        os.remove(dummy_log + ".index")
