"""业务适配器注册表。新增模块只扩展适配器，不在引擎里判断业务字段。"""

from importlib import import_module

ADAPTERS = {"project": ("app.modules.business.project.adapter", "ProjectWorkflowAdapter")}


def adapter_for(business_key: str, db):
    if business_key not in ADAPTERS:
        raise ValueError("未注册此业务模块的流程适配器")
    module, name = ADAPTERS[business_key]
    return getattr(import_module(module), name)(db)
