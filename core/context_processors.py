def platform_context(request):
    result = {'product_name':'数构智学'}
    if request.user.is_authenticated:
        from apps.accounts.services.credential_service import get_config
        from core.llm.model_registry import MODEL_TIERS
        config = get_config(request.user)
        result.update(api_config=config,config=config,model_options=MODEL_TIERS,current_model_label=MODEL_TIERS[config.default_tier].label,key_configured=config.configured)
    return result
