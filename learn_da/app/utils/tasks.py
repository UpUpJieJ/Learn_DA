from app.utils.logger import log


# ========================================
# 示例 1: 使用 FastAPI 内置的 BackgroundTasks
# ========================================

def send_welcome_email_background(user_email: str, user_name: str):
    """
    发送欢迎邮件的后台任务
    
    这是一个使用 FastAPI BackgroundTasks 的示例
    
    Args:
        user_email: 用户邮箱
        user_name: 用户名
    
    使用示例:
        from fastapi import BackgroundTasks, APIRouter
        
        router = APIRouter()
        
        @router.post("/auth/register")
        async def register(
            user: UserCreate,
            background_tasks: BackgroundTasks,
            auth_service: AuthService = Depends(get_auth_service)
        ):
            # 创建用户
            await auth_service.create_user(user)
            
            # 添加后台任务：发送欢迎邮件
            background_tasks.add_task(
                send_welcome_email_background,
                user.email,
                user.username
            )
            
            return StdResp.success(msg="User created successfully")
    """
    import time
    log.info(f"开始发送欢迎邮件给 {user_email}")

    # 模拟发送邮件的耗时操作
    time.sleep(2)

    # 这里应该是实际的邮件发送逻辑
    # 例如：使用 SMTP 或邮件服务 API
    log.info(f"欢迎邮件已发送给 {user_email} ({user_name})")

    return {
        "email": user_email,
        "status": "sent",
        "timestamp": time.time()
    }


def log_user_action_background(user_id: int, action: str, details: dict = None):
    """
    记录用户操作的后台任务
    
    这是一个使用 FastAPI BackgroundTasks 的示例
    
    Args:
        user_id: 用户ID
        action: 操作类型（如：login, logout, update_profile）
        details: 操作详情
    
    使用示例:
        @router.post("/auth/login")
        async def login(
            user_login: UserLogin,
            background_tasks: BackgroundTasks,
            auth_service: AuthService = Depends(get_auth_service)
        ):
            login_response = await auth_service.login_user(user_login)
            
            # 添加后台任务：记录登录日志
            background_tasks.add_task(
                log_user_action_background,
                login_response.user.id,
                "login",
                {"ip": "192.168.1.1", "timestamp": time.time()}
            )
            
            return StdResp.success(data=login_response)
    """
    import time
    log.info(f"记录用户操作: user_id={user_id}, action={action}")

    # 模拟记录到数据库或日志文件
    time.sleep(0.5)

    log.info(f"用户操作已记录: user_id={user_id}, action={action}, details={details}")

    return {
        "user_id": user_id,
        "action": action,
        "logged_at": time.time()
    }


# ========================================
# 示例 2: 使用 fastapi_utils 的 repeat_every 定时任务
# ========================================

def statistics_task():
    """
    生成统计的定时任务
    
    这是一个使用 fastapi_utils repeat_every 的定时任务示例
    
    使用场景:
        - 统计最近 API 调用次数

    """
    import time
    from datetime import datetime

    log.info("开始生成每日统计...")
    time.sleep(1)
    statistics = {
        "date": datetime.now().strftime("%Y-%m-%d-%H:%M:%S"),
        "api_calls": 7890,
    }

    log.info(f"每日统计生成完成: {statistics}")
    return statistics


# ========================================
# 使用指南
# ========================================

"""
BackgroundTasks vs Repeat Every 使用指南:

1. BackgroundTasks (FastAPI 内置)
   - 适合一次性任务
   - 在路由中使用
   - 无需额外依赖
   - 示例：发送邮件、记录日志
   
   使用方式:
   from fastapi import BackgroundTasks
   
   @app.post("/endpoint")
   async def endpoint(background_tasks: BackgroundTasks):
       background_tasks.add_task(task_function, arg1, arg2)
       return {"message": "Task started"}

2. Repeat Every (fastapi_utils)
   - 适合周期性任务
   - 需要安装 fastapi-utils
   - 在 main.py 中使用装饰器
   - 示例：清理数据、生成报表
   
   使用方式:
   # 安装依赖
   pip install fastapi-utils
   
   # 在 main.py 中配置
   from fastapi import FastAPI
   from fastapi_utils.tasks import repeat_every
   
   app = FastAPI()
   
   @app.on_event("startup")
   @repeat_every(seconds=60*5)
   async def cleanup_task():
       from app.utils.tasks import cleanup_expired_tokens_task
       await cleanup_expired_tokens_task()
   
   # 启动应用
   uvicorn main:app --reload

3. Celery Beat (你已经集成)
   - 适合复杂的周期性任务
   - 需要配置 Celery
   - 在 celery_app.py 中配置
   - 示例：发送邮件、长时间运行的任务
   
   使用方式:
   # 在 app/tasks/celery_app.py 中配置
   celery_app.conf.beat_schedule = {
       'task-name': {
           'task': 'app.tasks.user_tasks.check_unverified_users_task',
           'schedule': timedelta(hours=1),
       },
   }
   
   # 启动 Celery Beat
   celery -A app.tasks.celery_app beat --loglevel=info

选择建议:
- 简单的一次性任务 → 使用 BackgroundTasks
- 简单的周期性任务（< 30秒）→ 使用 Repeat Every (fastapi_utils)
- 复杂的周期性任务或耗时任务 → 使用 Celery Beat（你已经集成）
- 需要持久化和监控 → 使用 Celery Beat
- 快速响应需求 → 使用 BackgroundTasks
"""
