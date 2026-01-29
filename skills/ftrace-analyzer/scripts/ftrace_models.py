import dataclasses
from typing import Dict, Any, Optional

@dataclasses.dataclass
class Event:
    task: str
    pid: int
    cpu: int
    irqs: str
    timestamp: float
    event_type: str
    details: str
    raw_line: str
    line_no: Optional[int] = None
    prev_comm: Optional[str] = None
    prev_pid: Optional[int] = None
    prev_prio: Optional[int] = None
    prev_state: Optional[str] = None
    next_comm: Optional[str] = None
    next_pid: Optional[int] = None
    next_prio: Optional[int] = None
    
    def __str__(self):
        prefix = f"{self.line_no}: " if self.line_no is not None else ""
        return f"{prefix}[{self.timestamp:.6f}] CPU{self.cpu} {self.task}-{self.pid} {self.event_type}: {self.details}"

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)
