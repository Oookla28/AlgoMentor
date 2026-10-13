"""Track provider failures separately from legitimate student-code verdicts."""
from functools import wraps
from core.exceptions import CodeExecutionError
from core.services.availability import ServiceAvailabilityManager
from .provider import ExecutionLimits, validate_program


def track_execution(function):
    @wraps(function)
    def run(self, source, stdin='', limits=ExecutionLimits()):
        validate_program(source, stdin, limits)
        manager = ServiceAvailabilityManager('code_execution')
        if not manager.begin_attempt():
            raise CodeExecutionError('隔离执行服务暂不可用，可继续编辑代码和查看历史结果；稍后重试。本次不计入成绩。',
                                     code='EXECUTION_TEMPORARILY_UNAVAILABLE')
        try:
            result = function(self, source, stdin, limits)
        except CodeExecutionError as exc:
            manager.record_failure(exc.code)
            raise
        # Syntax/runtime/time-limit verdicts prove the sandbox executed a real job.
        manager.record_success()
        return result
    return run
