from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.models import User

from .depends import get_auth_service
from .schemas import UserCreate, UserLogin, UserUpdate
from .schemas_res import Token, UserLoginResponse, UserResponse
from .service import AuthService
from ..utils.base_response import StdResp
from ..utils.limiter import limiter
from ..utils.pagination import PaginationResult
from ..utils.security import get_current_user, jwt_security_service, oauth2_scheme

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=StdResp, summary="用户注册")
@limiter.limit("30/minute")
async def register(
    request: Request,
    user: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
):
    base_url = str(request.base_url)
    await auth_service.create_user(user, base_url=base_url)
    return StdResp.success(msg="User created successfully, verification email sent")


@router.get("/verify-email", response_model=StdResp[UserResponse], summary="验证邮箱")
async def verify_email(
    token: str = Query(...),
    auth_service: AuthService = Depends(get_auth_service),
):
    user = await auth_service.verify_email_token(token)
    return StdResp.success(data=user, msg="Email verified successfully")


@router.post("/token", response_model=Token, summary="swagger认证专用接口")
@limiter.limit("10/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
):
    user_login = UserLogin(username=form_data.username, password=form_data.password)
    login_response = await auth_service.login_user(user_login)
    return Token(
        access_token=login_response.access_token,
        token_type=login_response.token_type,
    )


@router.post("/login", response_model=StdResp[UserLoginResponse], summary="用户登录")
@limiter.limit("10/minute")
async def login(
    request: Request,
    user_login: UserLogin,
    auth_service: AuthService = Depends(get_auth_service),
):
    login_response = await auth_service.login_user(user_login)
    return StdResp.success(data=login_response, msg="Login successful")


@router.get("/me", response_model=StdResp[UserResponse], summary="获取当前用户信息")
async def read_users_me(current_user: User = Depends(get_current_user)):
    user_response = UserResponse.model_validate(current_user)
    return StdResp.success(data=user_response, msg="User information retrieved successfully")


@router.patch("/me", response_model=StdResp[UserResponse], summary="更新当前用户信息")
@limiter.limit("10/minute")
async def update_user_info(
    request: Request,
    update_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    auth_service: AuthService = Depends(get_auth_service),
):
    updated_user = await auth_service.update_user_info(current_user.id, update_data)
    return StdResp.success(data=updated_user, msg="User information updated successfully")


@router.post("/logout", response_model=StdResp, summary="用户登出")
async def logout(
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
):
    await jwt_security_service.add_token_to_blacklist(token)
    return StdResp.success(msg="Logged out successfully")


@router.get("/users", response_model=StdResp[PaginationResult[UserResponse]], summary="获取用户列表")
@limiter.limit("10/minute")
async def get_users(
    request: Request,
    page: int = 1,
    size: int = 10,
    auth_service: AuthService = Depends(get_auth_service),
    current_user: User = Depends(get_current_user),
):
    pagination_result = await auth_service.get_all_users(page, size)
    return StdResp.success(data=pagination_result, msg="Users retrieved successfully")


@router.get("/users/{user_id}", response_model=StdResp[UserResponse], summary="获取用户信息")
async def get_user_by_id(
    request: Request,
    user_id: int,
    auth_service: AuthService = Depends(get_auth_service),
    # current_user: User = Depends(get_current_user),
):
    user = await auth_service.get_user_by_id(user_id)
    if user is None:
        return StdResp.error(msg="User not found", code=404)
    return StdResp.success(data=user, msg="User retrieved successfully")
