"""
MinIO文件存储服务模块
提供文件上传、下载和URL生成等功能
"""
import base64
import json
from datetime import datetime, timezone, timedelta
from typing import BinaryIO, Optional, Dict, Any

import boto3
from urllib.parse import urlparse
from config.settings import settings


class MinIOService:
    """
    MinIO服务类 - 轻量级实现
    提供文件的上传、下载、预签名URL等核心功能
    """

    def __init__(self):
        """初始化MinIO客户端"""
        self._client = None
        self.endpoint_url = settings.MINIO_ENDPOINT
        self.access_key = settings.MINIO_ACCESS_KEY
        self.secret_key = settings.MINIO_SECRET_KEY
        self.bucket_name = settings.BUCKET_NAME

    @property
    def client(self):
        """懒加载客户端"""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self):
        """创建并返回MinIO客户端实例"""
        return boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=boto3.session.Config(signature_version='s3v4'),
        )

    def _ensure_bucket_policy(self):
        """确保桶策略已设置"""
        try:
            # 检查桶是否存在
            self.client.head_bucket(Bucket=self.bucket_name)
        except:
            # 如果桶不存在则创建
            self.client.create_bucket(Bucket=self.bucket_name)

        # 设置桶策略
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    f"arn:aws:s3:::{self.bucket_name}",
                    f"arn:aws:s3:::{self.bucket_name}/*"
                ]
            }]
        }
        try:
            self.client.put_bucket_policy(
                Bucket=self.bucket_name,
                Policy=json.dumps(bucket_policy)
            )
        except:
            pass  # 策略可能已存在

    def _normalize_object_name(self, object_name: str) -> str:
        """规范化对象名：提取URL中的key"""
        if '://' in object_name:
            parsed = urlparse(object_name)
            path = parsed.path.lstrip('/')
            if path.startswith(f"{self.bucket_name}/"):
                return path[len(self.bucket_name)+1:]
            return path
        return object_name

    def upload(self, content: bytes, filename: str, metadata: Optional[Dict[str, str]] = None) -> str:
        """上传文件到MinIO - 简化版本

        Args:
            content: 文件内容
            filename: 文件名（将用于构建object key）
            metadata: 可选的元数据

        Returns:
            str: object key
        """
        self._ensure_bucket_policy()

        # 生成object key: 日期/UUID_原始文件名
        timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d")
        unique_id = self._generate_short_id()
        object_name = f"{timestamp}/{unique_id}_{filename}"

        # 准备元数据
        final_metadata = {}
        if metadata:
            final_metadata.update(metadata)
        # 自动添加原始文件名到metadata
        final_metadata["original-filename"] = base64.b64encode(filename.encode('utf-8')).decode('ascii')

        # 上传文件
        put_kwargs = {
            "Bucket": self.bucket_name,
            "Key": object_name,
            "Body": content,
            "ContentType": self._get_content_type(filename)
        }
        if final_metadata:
            put_kwargs["Metadata"] = final_metadata

        self.client.put_object(**put_kwargs)
        return object_name

    def get(self, object_name: str) -> tuple[bytes, Dict[str, Any]]:
        """获取文件内容和元数据

        Args:
            object_name: 对象名称

        Returns:
            tuple[content, metadata]: 文件内容和元数据

        Raises:
            ClientError: 当文件不存在时抛出异常
        """
        try:
            response = self.client.get_object(
                Bucket=self.bucket_name,
                Key=self._normalize_object_name(object_name)
            )
            content = response['Body'].read()
            metadata = response.get('Metadata', {})
            return content, metadata
        except self.client.exceptions.NoSuchKey:
            raise Exception(f"文件不存在: {object_name}")
        except self.client.exceptions.ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                raise Exception(f"文件不存在: {object_name}")
            else:
                raise e

    def delete(self, object_name: str) -> None:
        """删除文件

        Args:
            object_name: 对象名称
        """
        self.client.delete_object(
            Bucket=self.bucket_name,
            Key=self._normalize_object_name(object_name)
        )

    def generate_presigned_url(self, object_name: str, expires_in: int = 3600) -> str:
        """生成预签名URL

        Args:
            object_name: 对象名称
            expires_in: 过期时间（秒），默认1小时

        Returns:
            str: 预签名URL
        """
        return self.client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket_name, 'Key': self._normalize_object_name(object_name)},
            ExpiresIn=expires_in
        )

    def get_url(self, object_name: str) -> str:
        """获取公开访问URL

        Args:
            object_name: 对象名称

        Returns:
            str: 公开URL
        """
        return f"{self.endpoint_url}/{self.bucket_name}/{object_name}"

    # 工具方法
    def _generate_short_id(self) -> str:
        """生成短UUID"""
        import uuid
        return str(uuid.uuid4()).replace('-', '')[:16]

    def _get_content_type(self, filename: str) -> str:
        """根据文件名获取MIME类型"""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"


# 全局单例实例
minio_service = MinIOService()