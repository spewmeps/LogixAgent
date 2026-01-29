# Ftrace 日志解析器 - 面向分析流程的接口设计

**项目名称**: FTrace Parser  
**版本**: v2.0  
**设计理念**: 支持交互式、探索式分析流程

---

## 1. 设计理念

### 核心思想

根据实际的 ftrace 分析流程，分析师需要：

1. **先总览**：了解日志的基本情况（时间范围、规模、涉及哪些任务）
2. **再定位**：根据初步观察，缩小关注范围
3. **深入查**：针对可疑点进行详细分析
4. **来回看**：在不同视角间切换，验证假设

因此接口设计必须支持：
- ✅ 快速获取文件元信息
- ✅ 灵活的过滤和查询
- ✅ 多次调用不重复解析
- ✅ 按需加载，节省内存
- ✅ 支持分析流程的"对话式"调用

---

## 2. 核心架构

### 2.1 三层架构

```
┌─────────────────────────────────────┐
│   Analysis API (分析接口层)          │  高层次分析接口
│   - 时间断层检测                      │
│   - 调度抖动分析                      │
│   - 上下文分类                        │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│   Query API (查询接口层)             │  灵活查询接口
│   - 按时间范围查询                    │
│   - 按进程/CPU查询                    │
│   - 过滤和聚合                        │
└─────────────────────────────────────┘
              ↓
┌─────────────────────────────────────┐
│   TraceFile (文件管理层)             │  文件元信息和索引
│   - 元数据缓存                        │
│   - 索引构建                          │
│   - 流式读取                          │
└─────────────────────────────────────┘
```

---

## 3. TraceFile 类 - 文件总接口

### 3.1 设计目标

提供文件级别的元信息和快速访问能力，是所有分析的入口。

### 3.2 接口设计

```python
class TraceFile:
    """
    Ftrace 日志文件的总接口
    
    职责：
    1. 提供文件元信息（不解析全部内容）
    2. 构建索引以支持快速查询
    3. 管理内存和缓存
    """
    
    def __init__(self, filepath: str, 
                 index_by: List[str] = ['timestamp', 'cpu', 'pid'],
                 lazy_load: bool = True):
        """
        Args:
            filepath: ftrace 日志文件路径
            index_by: 构建哪些索引（用于加速查询）
            lazy_load: 是否延迟加载（True=不立即解析全部）
        """
        
    # ==================== 文件基础信息 ====================
    
    def info(self) -> Dict:
        """
        获取文件元信息（快速，不解析全部内容）
        
        Returns:
            {
                'filepath': '/path/to/trace.txt',
                'file_size': '2.3 GB',
                'line_count': 10234567,  # 估算值
                'time_range': {
                    'start': 7541.834045,
                    'end': 7641.834045,
                    'duration': 100.0  # 秒
                },
                'event_types': ['sched_switch', 'sched_wakeup'],
                'cpu_count': 8,
                'process_count': 234,  # 唯一进程数
                'indexed': True
            }
        """
        
    def summary(self) -> str:
        """
        返回友好的文本摘要
        
        Returns:
            '''
            Ftrace 日志摘要
            ===============
            文件: trace.txt (2.3 GB)
            时间范围: 7541.834 - 7641.834 (100.00 秒)
            事件数: ~10,234,567 行
            CPU 数: 8 (CPU 0-7)
            进程数: 234 个
            事件类型: sched_switch, sched_wakeup
            索引: ✓ (timestamp, cpu, pid)
            '''
        """
        
    # ==================== 快速统计 ====================
    
    def get_time_range(self) -> Tuple[float, float]:
        """获取时间范围 (start, end)"""
        
    def get_duration(self) -> float:
        """获取总时长（秒）"""
        
    def get_event_count(self) -> int:
        """获取事件总数（精确值，需要扫描）"""
        
    def get_cpus(self) -> List[int]:
        """获取涉及的 CPU 列表"""
        
    def get_processes(self) -> List[Dict]:
        """
        获取所有进程信息
        
        Returns:
            [
                {'pid': 3711, 'comm': 'kube-apiserver', 'type': 'user'},
                {'pid': 7828, 'comm': 'kworker/u16:0', 'type': 'kernel'},
                ...
            ]
        """
        
    def get_process_types(self) -> Dict[str, List[Dict]]:
        """
        按类型分组返回进程（支持第二层分析）
        
        Returns:
            {
                'user': [{'pid': 3711, 'comm': 'kube-apiserver'}, ...],
                'kernel_thread': [{'pid': 7828, 'comm': 'kworker/u16:0'}, ...],
                'idle': [{'pid': 0, 'comm': 'swapper/0'}, ...],
                'irq': [],  # 如果日志中有
                'softirq': []
            }
        """
        
    # ==================== 索引管理 ====================
    
    def build_index(self, force: bool = False):
        """
        构建索引（加速后续查询）
        
        Args:
            force: 是否强制重建索引
            
        Note:
            索引文件保存为 .ftrace_index
            首次调用会扫描文件，后续直接加载
        """
        
    def has_index(self) -> bool:
        """是否已有索引"""
        
    # ==================== 查询接口 ====================
    
    def query(self) -> 'QueryBuilder':
        """
        返回查询构造器（链式调用）
        
        Example:
            trace.query()\
                 .time_range(7541.0, 7542.0)\
                 .cpu(0, 1, 2)\
                 .pid(3711)\
                 .execute()
        """
```

---

## 4. QueryBuilder 类 - 灵活查询接口

### 4.1 设计目标

支持链式调用，灵活组合查询条件，满足分析流程中的"逐步缩小范围"需求。

### 4.2 接口设计

```python
class QueryBuilder:
    """
    查询构造器（支持链式调用）
    
    设计理念：
    - 每个方法返回 self，支持链式调用
    - 条件逐步累加
    - 最后调用 execute() 执行查询
    """
    
    # ==================== 时间维度 ====================
    
    def time_range(self, start: float, end: float) -> 'QueryBuilder':
        """
        限制时间范围
        
        Args:
            start: 起始时间戳
            end: 结束时间戳
            
        Example:
            query.time_range(7541.0, 7542.0)
        """
        
    def time_slice(self, duration: float, offset: float = 0) -> 'QueryBuilder':
        """
        从文件开头取指定时长的数据
        
        Args:
            duration: 时长（秒）
            offset: 偏移（秒）
            
        Example:
            query.time_slice(1.0)  # 前1秒
            query.time_slice(1.0, offset=10.0)  # 第10-11秒
        """
        
    def around_time(self, timestamp: float, window: float = 0.1) -> 'QueryBuilder':
        """
        查询某个时间点附近的事件
        
        Args:
            timestamp: 中心时间戳
            window: 前后窗口大小（秒）
            
        Example:
            query.around_time(7541.834045, window=0.01)  # 前后10ms
        """
        
    # ==================== 空间维度（CPU/进程） ====================
    
    def cpu(self, *cpus: int) -> 'QueryBuilder':
        """
        限制 CPU
        
        Example:
            query.cpu(0, 1, 2)
        """
        
    def pid(self, *pids: int) -> 'QueryBuilder':
        """
        限制进程 ID
        
        Example:
            query.pid(3711, 2634)
        """
        
    def comm(self, *names: str, pattern: str = None) -> 'QueryBuilder':
        """
        限制进程名
        
        Args:
            names: 精确匹配的进程名
            pattern: 正则表达式模式
            
        Example:
            query.comm('kube-apiserver', 'containerd')
            query.comm(pattern=r'kworker.*')
        """
        
    def process_type(self, *types: str) -> 'QueryBuilder':
        """
        限制进程类型
        
        Args:
            types: 'user', 'kernel_thread', 'idle', 'irq', 'softirq'
            
        Example:
            query.process_type('kernel_thread')
        """
        
    # ==================== 事件属性 ====================
    
    def prev_state(self, *states: str) -> 'QueryBuilder':
        """
        限制 prev_state
        
        Example:
            query.prev_state('S', 'D')  # 只看睡眠和不可中断睡眠
        """
        
    def event_type(self, *types: str) -> 'QueryBuilder':
        """
        限制事件类型
        
        Example:
            query.event_type('sched_switch', 'sched_wakeup')
        """
        
    # ==================== 聚合和排序 ====================
    
    def group_by(self, *fields: str) -> 'QueryBuilder':
        """
        分组聚合
        
        Args:
            fields: 'cpu', 'pid', 'comm', 'prev_state'
            
        Example:
            query.group_by('cpu')
        """
        
    def order_by(self, field: str, ascending: bool = True) -> 'QueryBuilder':
        """
        排序
        
        Example:
            query.order_by('timestamp')
        """
        
    def limit(self, n: int) -> 'QueryBuilder':
        """
        限制返回数量
        
        Example:
            query.limit(100)
        """
        
    # ==================== 执行查询 ====================
    
    def execute(self) -> 'QueryResult':
        """
        执行查询，返回结果对象
        
        Returns:
            QueryResult 对象
        """
        
    def count(self) -> int:
        """
        只返回匹配的事件数量（不加载数据）
        
        Example:
            count = trace.query().cpu(0).time_range(7541, 7542).count()
        """
        
    def first(self, n: int = 1) -> List[Event]:
        """
        返回前 N 个事件
        
        Example:
            events = trace.query().cpu(0).first(10)
        """
        
    def to_dataframe(self) -> 'pandas.DataFrame':
        """
        转换为 pandas DataFrame（可选）
        
        Example:
            df = trace.query().cpu(0, 1).to_dataframe()
        """
```

---

## 5. QueryResult 类 - 查询结果

### 5.1 接口设计

```python
class QueryResult:
    """
    查询结果容器
    
    职责：
    1. 持有查询到的事件
    2. 提供多种视角的访问方式
    3. 支持进一步过滤和分析
    """
    
    def __init__(self, events: List[Event]):
        """
        Args:
            events: 事件列表
        """
        
    # ==================== 基础访问 ====================
    
    def __len__(self) -> int:
        """返回事件数量"""
        
    def __getitem__(self, index) -> Event:
        """支持索引访问"""
        
    def __iter__(self):
        """支持迭代"""
        
    @property
    def events(self) -> List[Event]:
        """返回所有事件"""
        
    # ==================== 统计信息 ====================
    
    def summary(self) -> Dict:
        """
        返回统计摘要
        
        Returns:
            {
                'count': 1234,
                'time_range': (7541.0, 7542.0),
                'cpus': [0, 1, 2],
                'processes': [3711, 2634],
                'state_distribution': {'S': 456, 'R': 789}
            }
        """
        
    def describe(self) -> str:
        """
        返回友好的文本描述
        
        Returns:
            '''
            查询结果摘要
            ===========
            事件数: 1,234
            时间范围: 7541.0 - 7542.0 (1.0 秒)
            涉及 CPU: 0, 1, 2
            涉及进程: 3 个
            状态分布: S(456), R(789)
            '''
        """
        
    # ==================== 分组视图 ====================
    
    def by_cpu(self) -> Dict[int, List[Event]]:
        """
        按 CPU 分组
        
        Returns:
            {
                0: [event1, event2, ...],
                1: [event3, event4, ...],
            }
        """
        
    def by_process(self) -> Dict[int, List[Event]]:
        """
        按进程 ID 分组
        
        Returns:
            {
                3711: [event1, event2, ...],
                2634: [event3, event4, ...],
            }
        """
        
    def by_state(self) -> Dict[str, List[Event]]:
        """
        按 prev_state 分组
        
        Returns:
            {
                'S': [event1, event2, ...],
                'R': [event3, event4, ...],
            }
        """
        
    # ==================== 时间序列视图 ====================
    
    def timeline(self, bin_size: float = 0.001) -> Dict:
        """
        生成时间线视图（用于查看事件分布）
        
        Args:
            bin_size: 时间桶大小（秒）
            
        Returns:
            {
                'bins': [7541.0, 7541.001, 7541.002, ...],
                'counts': [12, 34, 23, ...],
                'events_per_bin': [[e1, e2], [e3, e4], ...]
            }
        """
        
    # ==================== 导出 ====================
    
    def to_text(self, format: str = 'table') -> str:
        """
        导出为文本格式
        
        Args:
            format: 'table', 'list', 'raw'
        """
        
    def to_json(self) -> str:
        """导出为 JSON"""
        
    def to_csv(self, filepath: str = None) -> str:
        """导出为 CSV"""
        
    # ==================== 进一步查询 ====================
    
    def filter(self, func: Callable[[Event], bool]) -> 'QueryResult':
        """
        基于自定义函数过滤
        
        Example:
            result.filter(lambda e: e.next_pid != 0)
        """
```

---

## 6. 分析接口层 - 高层次分析

### 6.1 设计目标

封装常见分析模式，支持"分析流程"文档中的各层分析需求。

### 6.2 接口设计

```python
class Analyzer:
    """
    高层次分析接口
    
    对应分析流程的各个层次：
    - 第一层：时间尺度和卡顿级别
    - 第二层：执行上下文分区
    - 第三层：业务运行状态
    - 第四层：调度视角
    - 第五层：中断责任
    """
    
    def __init__(self, trace: TraceFile):
        """
        Args:
            trace: TraceFile 对象
        """
        
    # ==================== 第一层：时间尺度识别 ====================
    
    def detect_time_anomalies(self, 
                             threshold_us: float = 100) -> Dict:
        """
        检测时间异常
        
        Args:
            threshold_us: 异常阈值（微秒）
            
        Returns:
            {
                'gaps': [
                    {
                        'start': 7541.834,
                        'end': 7541.835,
                        'duration_us': 1000,
                        'prev_event': Event(...),
                        'next_event': Event(...)
                    },
                    ...
                ],
                'summary': {
                    'total_gaps': 12,
                    'max_gap_us': 5000,
                    'p95_gap_us': 1200
                }
            }
        """
        
    def get_time_distribution(self, bin_size: float = 0.001) -> Dict:
        """
        获取时间分布（用于识别热点时段）
        
        Args:
            bin_size: 时间桶大小（秒）
            
        Returns:
            {
                'bins': [...],
                'event_counts': [...],
                'cpu_util': [0.45, 0.67, 0.89, ...],  # 每个桶的利用率
                'hotspots': [  # 高负载时段
                    {'start': 7543.123, 'end': 7545.678, 'util': 0.91},
                    ...
                ]
            }
        """
        
    # ==================== 第二层：执行上下文分区 ====================
    
    def classify_contexts(self) -> Dict:
        """
        将事件按执行上下文分类
        
        Returns:
            {
                'user_process': {
                    'count': 1234,
                    'processes': [3711, 2634, ...],
                    'time_percent': 45.67
                },
                'kernel_thread': {
                    'count': 5678,
                    'threads': ['kworker/u16:0', ...],
                    'time_percent': 23.45
                },
                'idle': {
                    'count': 890,
                    'time_percent': 30.88
                },
                'irq': {...},
                'softirq': {...}
            }
        """
        
    def get_context_timeline(self, cpu: int) -> List[Dict]:
        """
        获取某个 CPU 的上下文切换时间线
        
        Args:
            cpu: CPU 编号
            
        Returns:
            [
                {
                    'start': 7541.834,
                    'end': 7541.835,
                    'context': 'user_process',
                    'pid': 3711,
                    'comm': 'kube-apiserver'
                },
                {
                    'start': 7541.835,
                    'end': 7541.836,
                    'context': 'idle',
                    'pid': 0,
                    'comm': 'swapper/0'
                },
                ...
            ]
        """
        
    # ==================== 第三层：业务运行状态 ====================
    
    def check_process_running(self, pid: int, 
                             time_range: Tuple[float, float] = None) -> Dict:
        """
        检查进程是否在运行
        
        Args:
            pid: 进程 ID
            time_range: 时间范围
            
        Returns:
            {
                'is_running': True,
                'run_time': 12.34,  # 秒
                'run_percent': 45.67,
                'sched_count': 234,
                'avg_timeslice_ms': 19.47,
                'gaps': [  # 长时间未运行的时段
                    {'start': 7543.0, 'end': 7548.0, 'duration': 5.0},
                    ...
                ]
            }
        """
        
    def compare_cpu_time(self, *pids: int) -> Dict:
        """
        比较多个进程的 CPU 时间占用
        
        Args:
            pids: 进程 ID 列表
            
        Returns:
            {
                3711: {'time': 45.67, 'percent': 45.67},
                2634: {'time': 23.45, 'percent': 23.45},
                ...
            }
        """
        
    # ==================== 第四层：调度视角 ====================
    
    def detect_time_gaps(self, pid: int = None, 
                        threshold_ms: float = 1.0) -> List[Dict]:
        """
        检测时间断层（用于发现"进程去哪了"）
        
        Args:
            pid: 进程 ID（None=所有进程）
            threshold_ms: 间隔阈值（毫秒）
            
        Returns:
            [
                {
                    'pid': 3711,
                    'comm': 'kube-apiserver',
                    'gap_start': 7541.834,
                    'gap_end': 7542.335,
                    'duration_ms': 501.0,
                    'last_seen': Event(...),
                    'next_seen': Event(...),
                    'cpu_activity': {  # 这段时间 CPU 在做什么
                        'dominant_context': 'kernel_thread',
                        'processes': ['kworker/u16:0', ...]
                    }
                },
                ...
            ]
        """
```
