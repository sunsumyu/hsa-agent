
import time
import functools
import inspect
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from loguru import logger

console = Console()

class PerfMonitor:
    """
    [企业级] 性能监控中间件：提供毫秒级耗时追踪与 Rich 可视化输出。
    """
    
    @staticmethod
    def time_it(category: str):
        """
        耗时追踪装饰器。
        usage: @PerfMonitor.time_it("CLICKHOUSE_EXEC")
        """
        def decorator(func):
            if inspect.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args, **kwargs):
                    start_time = time.perf_counter()
                    result = await func(*args, **kwargs)
                    duration = (time.perf_counter() - start_time) * 1000
                    PerfMonitor.print_metric(category, func.__name__, duration)
                    return result
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args, **kwargs):
                    start_time = time.perf_counter()
                    result = func(*args, **kwargs)
                    duration = (time.perf_counter() - start_time) * 1000
                    PerfMonitor.print_metric(category, func.__name__, duration)
                    return result
                return sync_wrapper
        return decorator

    @staticmethod
    def print_metric(category: str, name: str, duration_ms: float):
        color = "green" if duration_ms < 500 else "yellow" if duration_ms < 2000 else "red"
        
        table = Table(show_header=False, box=None)
        table.add_row(
            f"[bold blue]⏱️  {category}[/bold blue]",
            f"[white]{name}[/white]",
            f"[{color}]{duration_ms:.2f} ms[/{color}]"
        )
        
        console.print(Panel(table, expand=False, border_style="cyan"))
        logger.info(f"PERF | {category} | {name} | {duration_ms:.2f}ms")

perf_monitor = PerfMonitor()
