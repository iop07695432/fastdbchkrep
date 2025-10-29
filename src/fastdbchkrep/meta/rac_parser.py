#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RAC多节点解析器模块
处理Oracle RAC集群的多节点数据合并和JSON生成
"""

import os
import re
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from loguru import logger


class RacNodeInfo:
    """RAC节点信息数据类"""
    
    def __init__(self, directory: str):
        """
        初始化RAC节点信息
        
        Args:
            directory: 节点目录路径
        """
        self.directory = directory
        self.dirname = os.path.basename(directory)
        self.hostname = None
        self.sid = None
        self.dbname = None
        self.collect_date = None
        self.file_status_path = None
        self.file_status_data = None
        
        # 解析目录名称
        self._parse_dirname()
        
        # 加载file_status.json
        self._load_file_status()
    
    def _parse_dirname(self):
        """
        解析目录名称，提取hostname、sid、日期
        
        目录命名格式示例:
        - oms-db1_hnoms1_20250826
        - oms-db2_hnoms2_20250826
        """
        parts = self.dirname.split('_')
        
        if len(parts) >= 3:
            # 标准格式: hostname_sid_date
            self.hostname = parts[0]
            self.sid = parts[1]
            self.collect_date = parts[2]
            
            # 从sid推导dbname（去除数字后缀）
            # hnoms1 -> hnoms, hnoms2 -> hnoms
            self.dbname = re.sub(r'\d+$', '', self.sid)
        else:
            logger.warning(f"非标准RAC目录命名格式: {self.dirname}")
    
    def _load_file_status(self):
        """加载file_status.json文件"""
        self.file_status_path = os.path.join(self.directory, 'file_status.json')
        
        if os.path.exists(self.file_status_path):
            try:
                with open(self.file_status_path, 'r', encoding='utf-8') as f:
                    self.file_status_data = json.load(f)
                    
                    # 从file_status.json提取/验证信息
                    if 'hostname' in self.file_status_data:
                        # 优先使用file_status.json中的hostname
                        self.hostname = self.file_status_data['hostname']
                    
                    if 'oracle_sid' in self.file_status_data:
                        self.sid = self.file_status_data['oracle_sid']
                    elif 'sid' in self.file_status_data:
                        self.sid = self.file_status_data['sid']
                    
                    # 重新从sid推导dbname
                    if self.sid:
                        self.dbname = re.sub(r'\d+$', '', self.sid)
                        
            except Exception as e:
                logger.error(f"加载file_status.json失败: {self.file_status_path}, 错误: {e}")
        else:
            logger.warning(f"file_status.json不存在: {self.file_status_path}")
    
    def is_valid(self) -> bool:
        """检查节点信息是否有效"""
        return all([self.hostname, self.sid, self.dbname, self.file_status_data])
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'hostname': self.hostname,
            'sid': self.sid,
            'dbname': self.dbname,
            'dirname': self.dirname,
            'collect_date': self.collect_date,
            'source_dir': self.directory
        }


class RacClusterInfo:
    """RAC集群信息类"""
    
    def __init__(self, nodes: List[RacNodeInfo]):
        """
        初始化RAC集群信息
        
        Args:
            nodes: RAC节点信息列表
        """
        self.nodes = nodes
        self.dbname = None
        self.cluster_name = None
        self.node_count = len(nodes)
        self.collect_date = None
        
        # 验证并提取集群信息
        self._extract_cluster_info()
    
    def _extract_cluster_info(self):
        """提取集群级别的信息"""
        if not self.nodes:
            raise ValueError("RAC集群至少需要一个节点")
        
        # 提取dbname（所有节点应该相同）
        dbnames = set(node.dbname for node in self.nodes if node.dbname)
        if len(dbnames) != 1:
            logger.warning(f"RAC节点间dbname不一致: {dbnames}")
            # 取第一个作为默认值
            self.dbname = list(dbnames)[0] if dbnames else None
        else:
            self.dbname = dbnames.pop()
        
        # 提取收集日期（所有节点应该相同）
        dates = set(node.collect_date for node in self.nodes if node.collect_date)
        if len(dates) != 1:
            logger.warning(f"RAC节点间收集日期不一致: {dates}")
            # 取最新的日期
            self.collect_date = max(dates) if dates else None
        else:
            self.collect_date = dates.pop()
        
        # 生成集群名称（基于hostname模式）
        # oms-db1, oms-db2 -> oms-db
        if self.nodes:
            hostname_base = re.sub(r'\d+$', '', self.nodes[0].hostname)
            self.cluster_name = hostname_base
    
    def validate_consistency(self) -> Tuple[bool, List[str]]:
        """
        验证节点间的一致性
        
        Returns:
            (是否一致, 问题列表)
        """
        issues = []
        
        # 检查dbname一致性
        dbnames = set(node.dbname for node in self.nodes if node.dbname)
        if len(dbnames) > 1:
            issues.append(f"数据库名称不一致: {dbnames}")
        
        # 检查日期一致性
        dates = set(node.collect_date for node in self.nodes if node.collect_date)
        if len(dates) > 1:
            issues.append(f"收集日期不一致: {dates}")
        
        # 检查必需文件
        for node in self.nodes:
            if not node.file_status_data:
                issues.append(f"节点{node.hostname}缺少file_status.json")
        
        # 检查db_model字段一致性
        db_models = set()
        for node in self.nodes:
            if node.file_status_data and 'db_model' in node.file_status_data:
                db_models.add(node.file_status_data['db_model'])
        
        if len(db_models) > 1:
            issues.append(f"数据库模式不一致: {db_models}")
        elif db_models and 'rac' not in db_models:
            issues.append(f"数据库模式不是RAC: {db_models}")
        
        return len(issues) == 0, issues
    
    def generate_identifier(self) -> str:
        """
        生成RAC集群的identifier
        
        格式: {cluster_name}_{dbname}_{date}
        示例: oms-db_hnoms_20250826
        """
        parts = []
        
        if self.cluster_name:
            parts.append(self.cluster_name)
        
        if self.dbname:
            parts.append(self.dbname)
        
        if self.collect_date:
            parts.append(self.collect_date)
        
        if parts:
            return '_'.join(parts)
        else:
            # 降级处理：使用第一个节点的目录名
            return self.nodes[0].dirname if self.nodes else 'unknown_rac'


class RacParser:
    """RAC多节点解析器"""
    
    @staticmethod
    def parse_rac_directories(directories: List[str]) -> RacClusterInfo:
        """
        解析RAC节点目录列表
        
        Args:
            directories: RAC节点目录路径列表
            
        Returns:
            RAC集群信息对象
        """
        if not directories:
            raise ValueError("至少需要一个RAC节点目录")
        
        # 解析每个节点
        nodes = []
        for directory in directories:
            if not os.path.exists(directory):
                logger.warning(f"目录不存在: {directory}")
                continue
            
            node = RacNodeInfo(directory)
            if node.is_valid():
                nodes.append(node)
                logger.info(f"成功解析RAC节点: {node.hostname} (SID: {node.sid})")
            else:
                logger.warning(f"无效的RAC节点目录: {directory}")
        
        if not nodes:
            raise ValueError("没有有效的RAC节点")
        
        # 创建集群信息
        cluster = RacClusterInfo(nodes)
        
        # 验证一致性
        is_consistent, issues = cluster.validate_consistency()
        if not is_consistent:
            logger.warning(f"RAC节点一致性检查发现问题: {issues}")
        
        return cluster
    
    @staticmethod
    def merge_node_files(cluster: RacClusterInfo) -> List[Dict[str, Any]]:
        """
        合并RAC节点的文件信息到metainfo数组
        
        Args:
            cluster: RAC集群信息
            
        Returns:
            metainfo数组
        """
        metainfo = []
        
        for idx, node in enumerate(cluster.nodes, 1):
            node_info = {
                'hostname': node.hostname,
                'sid': node.sid,
                'dbname': node.dbname,
                'collect_date': node.collect_date,
                'source_dir': node.directory,
                'node_info': {
                    'node_number': idx,
                    'node_name': f"node{idx}"
                },
                'files': {}
            }
            
            # 处理文件列表
            if node.file_status_data and 'files' in node.file_status_data:
                files_data = node.file_status_data['files']
                
                # 兼容files数组和对象两种格式
                if isinstance(files_data, list):
                    # 数组格式：转换为对象格式
                    for file_info in files_data:
                        if 'filename' in file_info and 'status' in file_info:
                            # 提取文件名前缀作为key
                            key = file_info['filename'].split('.')[0]
                            node_info['files'][key] = {
                                'filename': file_info['filename'],
                                'status': file_info['status'],
                                'description': file_info.get('description', ''),
                                'exists': file_info.get('exists', False),
                                'size': file_info.get('size', 0),
                                'path': os.path.join(node.directory, file_info['filename'])
                            }
                elif isinstance(files_data, dict):
                    # 对象格式：直接使用
                    for key, file_info in files_data.items():
                        if isinstance(file_info, dict):
                            file_info['path'] = os.path.join(
                                node.directory, 
                                file_info.get('filename', f"{key}.txt")
                            )
                            node_info['files'][key] = file_info
            
            # 添加验证状态
            node_info['validation_status'] = 'passed' if node.is_valid() else 'failed'
            
            metainfo.append(node_info)
        
        return metainfo
    
    @staticmethod
    def detect_rac_nodes(base_dir: str) -> List[str]:
        """
        自动检测RAC节点目录
        
        通过分析目录名称模式，自动识别属于同一RAC集群的节点
        
        Args:
            base_dir: 基础目录路径
            
        Returns:
            属于同一集群的节点目录列表
        """
        if not os.path.exists(base_dir):
            return []
        
        # 收集所有子目录
        subdirs = []
        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            if os.path.isdir(item_path):
                subdirs.append(item_path)
        
        # 按照RAC命名模式分组
        # 模式: {cluster_prefix}{node_num}_{sid}{instance_num}_{date}
        rac_groups = {}
        
        for subdir in subdirs:
            dirname = os.path.basename(subdir)
            
            # 尝试匹配RAC模式
            # 示例: oms-db1_hnoms1_20250826
            match = re.match(r'^(.+?)(\d+)_(.+?)(\d+)_(\d{8})$', dirname)
            if match:
                cluster_prefix = match.group(1)  # oms-db
                sid_prefix = match.group(3)      # hnoms
                date = match.group(5)            # 20250826
                
                # 生成分组key
                group_key = f"{cluster_prefix}_{sid_prefix}_{date}"
                
                if group_key not in rac_groups:
                    rac_groups[group_key] = []
                
                rac_groups[group_key].append(subdir)
        
        # 返回最大的RAC组
        if rac_groups:
            largest_group = max(rac_groups.values(), key=len)
            if len(largest_group) > 1:
                logger.info(f"自动检测到RAC集群节点: {[os.path.basename(d) for d in largest_group]}")
                return sorted(largest_group)  # 按名称排序确保顺序一致
        
        return []