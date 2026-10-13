from dataclasses import asdict,is_dataclass
from apps.problems.services.submission_service import run_code
from core.exceptions import ValidationError
from core.security.permissions import require_user


def execute_python_code(user,code: str,stdin: str = '',test_cases: list[dict] | None = None) -> dict:
    require_user(user)
    if not code.strip() or len(code)>20000 or len(stdin)>10000:
        raise ValidationError('代码或输入为空或超出长度限制。')
    if test_cases and len(test_cases)>5:
        raise ValidationError('智能体单次最多运行 5 个测试用例。')
    def run(value):
        result=run_code(user,code,value)
        return asdict(result) if is_dataclass(result) else result
    if not test_cases:
        return run(stdin)
    outputs=[]
    for case in test_cases:
        if not isinstance(case,dict) or not isinstance(case.get('stdin',''),str) or len(case.get('stdin',''))>10000:
            raise ValidationError('测试输入格式无效。')
        result=run(case.get('stdin',''))
        expected=case.get('expected_output')
        if expected is not None:
            result['expected_matches']=result.get('status')=='ACCEPTED' and str(result.get('stdout','')).strip()==str(expected).strip()
        outputs.append(result)
    return {'test_results':outputs,'note':'这些测试由用户或智能体提供，不构成题库正式提交。'}
