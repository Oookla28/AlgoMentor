class BusinessError(Exception):
    code = 'BUSINESS_ERROR'
    status_code = 400

    def __init__(self, message: str, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class ValidationError(BusinessError):
    code = 'VALIDATION_ERROR'


class AuthenticationError(BusinessError):
    code = 'AUTHENTICATION_ERROR'
    status_code = 401


class LLMProviderError(BusinessError):
    code = 'LLM_PROVIDER_ERROR'
    status_code = 502


class CodeExecutionError(BusinessError):
    code = 'CODE_EXECUTION_ERROR'
    status_code = 503


class KnowledgeRetrievalError(BusinessError):
    code = 'KNOWLEDGE_RETRIEVAL_ERROR'
    status_code = 503


class ReportGenerationError(BusinessError):
    code = 'REPORT_GENERATION_ERROR'
    status_code = 502


class ExternalServiceError(BusinessError):
    code = 'EXTERNAL_SERVICE_ERROR'
    status_code = 502
