
import os
import unittest
import tempfile
import json
from scripts.ftrace_file import TraceFile
from scripts.ftrace_analyzer import Analyzer

class TestQoSAnalyzer(unittest.TestCase):
    def setUp(self):
        self.test_file = tempfile.NamedTemporaryFile(mode='w+', delete=False)
        # Create a synthetic trace with QoS patterns on CPU 0
        # Gaps of 8ms every 20ms
        
        # Format: task-pid [cpu] irqs timestamp: event: details
        # Pattern:
        # t=0.000: event
        # t=0.012: event (gap 12ms - too big? no, 5-10ms is target. let's make 8ms gaps)
        
        # Let's simulate:
        # 0.000: run
        # 0.002: sleep
        # ... gap 8ms ...
        # 0.010: wakeup
        
        content = []
        base_time = 100.0
        
        # CPU 0: Regular 8ms gaps
        for i in range(10):
            # Active for 2ms
            content.append(f"task-{1000} [000] .... {base_time:.6f}: sched_switch: prev_comm=task prev_pid=1000 ...")
            
            # Gap of 8ms (QoS throttling)
            base_time += 0.008 
            
            content.append(f"task-{1000} [000] .... {base_time:.6f}: sched_switch: prev_comm=swapper/0 prev_pid=0 ...")
            
            base_time += 0.002
            
        # CPU 1: Random small gaps (should be ignored)
        base_time = 100.0
        for i in range(10):
             content.append(f"task-{2000} [001] .... {base_time:.6f}: sched_switch: ...")
             # Gaps: 1ms, 2ms, 3ms - all below 4ms min threshold
             base_time += (0.001 + (i % 3) * 0.001) 
        
        self.test_file.write('\n'.join(content))
        self.test_file.close()
        
    def tearDown(self):
        os.unlink(self.test_file.name)
        
    def test_qos_detection(self):
        trace = TraceFile(self.test_file.name)
        analyzer = Analyzer(trace)
        result = analyzer.detect_qos_patterns()
        
        print(json.dumps(result, indent=2))
        
        self.assertTrue(result['suspected_qos'])
        self.assertIn('cpu_0', result['details'])
        self.assertNotIn('cpu_1', result['details'])
        
        details = result['details']['cpu_0']
        self.assertEqual(details['confidence'], 'high')
        self.assertTrue(7.0 <= details['avg_duration_ms'] <= 9.0)

if __name__ == '__main__':
    unittest.main()
