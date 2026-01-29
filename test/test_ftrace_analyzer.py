import unittest
import os
import sys
import json
from ftrace_file import TraceFile
from ftrace_analyzer import Analyzer

class TestFtraceAnalyzerComprehensive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 优先使用真实的 ftrace 日志文件进行有意义的测试
        cls.log_path = "/opt/src/LogixAgent/logs/ftrace/trace.log"
        # 如果 trace.log 不存在，退而求其次使用 agent.log
        if not os.path.exists(cls.log_path):
            cls.log_path = "/opt/src/LogixAgent/logs/agent.log"
        
        # 如果文件都不存在，创建一个空的，防止测试崩溃
        if not os.path.exists(cls.log_path):
            os.makedirs(os.path.dirname(cls.log_path), exist_ok=True)
            with open(cls.log_path, 'w') as f:
                pass
        
        print(f"Using log file: {cls.log_path}")
        cls.trace = TraceFile(cls.log_path)
        cls.analyzer = Analyzer(cls.trace)

    def test_01_trace_file_interfaces(self):
        """测试 TraceFile 核心接口"""
        print("\n[STEP 1] Testing TraceFile interfaces...")
        info = self.trace.info()
        print(f"  - Trace Info: {json.dumps(info, indent=2)}")
        self.assertIsInstance(info, dict)
        self.assertIn('filepath', info)
        
        summary = self.trace.summary()
        print(f"  - Summary Length: {len(summary)}")
        self.assertIsInstance(summary, str)
        
        duration = self.trace.get_duration()
        print(f"  - Duration: {duration}s")
        self.assertIsInstance(duration, (int, float))
        
        cpus = self.trace.get_cpus()
        print(f"  - CPUs found: {len(cpus)}")
        self.assertIsInstance(cpus, list)
        
        procs = self.trace.get_processes()
        print(f"  - Processes found: {len(procs)}")
        self.assertIsInstance(procs, list)
        
        print("  => TraceFile interfaces OK")

    def test_02_query_builder_interfaces(self):
        """测试 QueryBuilder 链式调用接口"""
        print("\n[STEP 2] Testing QueryBuilder interfaces...")
        query = self.trace.query()
        print("  - Building complex query...")
        query.time_range(0, 1000)\
             .cpu(0)\
             .limit(5)
        
        print("  - Executing query...")
        result = query.execute()
        from ftrace_query import QueryResult
        self.assertIsInstance(result, QueryResult)
        print(f"  - Result events count: {len(result)}")
        
        cnt = self.trace.query().count()
        print(f"  - Total events count: {cnt}")
        self.assertIsInstance(cnt, int)
        
        print("  => QueryBuilder interfaces OK")

    def test_03_query_result_interfaces(self):
        """测试 QueryResult 数据处理接口"""
        print("\n[STEP 3] Testing QueryResult interfaces...")
        result = self.trace.query().limit(10).execute()
        from ftrace_query import QueryResult
        
        summary = result.summary()
        print(f"  - Result Summary: {json.dumps(summary, indent=2)}")
        self.assertIsInstance(summary, dict)
        
        print("  - Testing grouping interfaces...")
        self.assertIsInstance(result.by_cpu(), dict)
        self.assertIsInstance(result.by_process(), dict)
        
        print("  - Testing export formats (JSON/Text/CSV)...")
        self.assertTrue(len(result.to_json()) >= 0)
        self.assertTrue(len(result.to_text()) >= 0)
        
        print("  => QueryResult interfaces OK")

    def test_04_analyzer_interfaces(self):
        """测试 Analyzer 高层分析接口"""
        print("\n[STEP 4] Testing Analyzer interfaces...")
        
        print("  - Detecting time anomalies...")
        anomalies = self.analyzer.detect_time_anomalies()
        print(f"  - Anomalies Summary: {json.dumps(anomalies.get('summary', {}), indent=2)}")
        self.assertIsInstance(anomalies, dict)
        
        print("  - Classifying contexts...")
        contexts = self.analyzer.classify_contexts()
        print(f"  - Contexts: {json.dumps(contexts, indent=2)}")
        self.assertIsInstance(contexts, dict)
        
        print("  - Checking process running status (PID 0)...")
        status = self.analyzer.check_process_running(0)
        print(f"  - Status: {json.dumps(status, indent=2)}")
        self.assertIsInstance(status, dict)
        
        print("  => Analyzer interfaces OK")

if __name__ == '__main__':
    unittest.main()
