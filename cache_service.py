import redis
import json
import logging
from typing import Any, Optional, Dict, List, Union
from datetime import datetime, timedelta
import asyncio
from functools import wraps

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self, redis_url: str = None, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0):
        """
        Inicializa o serviço de cache com Redis e fallback para memória
        """
        # Cache L1 (memória) - sempre disponível
        self.memory_cache: Dict[str, Dict] = {}
                
        # Cache L2 (Redis) - pode falhar
        self.redis_client = None
        self.redis_available = False

        import os
        redis_url = os.getenv("REDIS_URL") or redis_url

        # TTLs específicos para diferentes tipos de dados
        self.ttls = {
            'classificacoes': 3600,     # 1 hora - dados estruturais
            'planos': 3600,             # 1 hora - dados estruturais  
            'itens': 3600,              # 1 hora - dados estruturais
            'lookups': 1800,            # 30 min - lookups de classificação
            'transacoes': 300,          # 5 min - dados transacionais
            'stats': 300,               # 5 min - estatísticas
            'pendentes': 60,            # 1 min - dados dinâmicos
            'default': 300              # 5 min - padrão
        }
                
        self._init_redis(redis_url, redis_host, redis_port, redis_db)

    def _init_redis(self, redis_url: str, redis_host: str, redis_port: int, redis_db: int):
        """Inicializa conexão Redis com tratamento de erro"""
        try:
            if redis_url:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
            else:
                self.redis_client = redis.Redis(
                    host=redis_host, 
                    port=redis_port, 
                    db=redis_db, 
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
            
            # Testa conexão
            self.redis_client.ping()
            self.redis_available = True
            logger.info("✅ Redis conectado com sucesso")
            
        except Exception as e:
            logger.warning(f"⚠️ Redis indisponível, usando apenas cache em memória: {e}")
            self.redis_available = False

    def _get_ttl(self, cache_type: str) -> int:
        """Retorna TTL apropriado para o tipo de cache"""
        return self.ttls.get(cache_type, self.ttls['default'])

    def _serialize_value(self, value: Any) -> str:
        """Serializa valor para armazenamento"""
        return json.dumps(value, ensure_ascii=False, default=str)

    def _deserialize_value(self, value: str) -> Any:
        """Deserializa valor do armazenamento"""
        try:
            return json.loads(value)
        except:
            return value

    def get(self, key: str, cache_type: str = 'default') -> Optional[Any]:
        """
        Busca valor no cache (L1 -> L2 -> None)
        """
        # L1: Memória
        if key in self.memory_cache:
            cache_data = self.memory_cache[key]
            if cache_data['expires_at'] > datetime.now():
                logger.debug(f"🎯 Cache L1 HIT: {key}")
                return cache_data['value']
            else:
                del self.memory_cache[key]

        # L2: Redis
        if self.redis_available:
            try:
                value = self.redis_client.get(key)
                if value:
                    logger.debug(f"🎯 Cache L2 HIT: {key}")
                    deserialized = self._deserialize_value(value)
                    
                    # Atualiza L1
                    ttl = self._get_ttl(cache_type)
                    self.memory_cache[key] = {
                        'value': deserialized,
                        'expires_at': datetime.now() + timedelta(seconds=ttl)
                    }
                    
                    return deserialized
            except Exception as e:
                logger.error(f"❌ Erro no Redis GET {key}: {e}")

        logger.debug(f"❌ Cache MISS: {key}")
        return None

    def set(self, key: str, value: Any, cache_type: str = 'default') -> bool:
        """
        Armazena valor no cache (L1 + L2)
        """
        ttl = self._get_ttl(cache_type)
        
        # L1: Memória
        self.memory_cache[key] = {
            'value': value,
            'expires_at': datetime.now() + timedelta(seconds=ttl)
        }
        
        # L2: Redis
        if self.redis_available:
            try:
                serialized = self._serialize_value(value)
                self.redis_client.setex(key, ttl, serialized)
                logger.debug(f"✅ Cache SET: {key} (TTL: {ttl}s)")
                return True
            except Exception as e:
                logger.error(f"❌ Erro no Redis SET {key}: {e}")
                return False
        
        logger.debug(f"✅ Cache SET (L1 only): {key}")
        return True

    def delete(self, key: str) -> bool:
        """Remove item específico do cache"""
        # L1
        if key in self.memory_cache:
            del self.memory_cache[key]
        
        # L2
        if self.redis_available:
            try:
                self.redis_client.delete(key)
                logger.debug(f"🗑️ Cache DELETE: {key}")
                return True
            except Exception as e:
                logger.error(f"❌ Erro no Redis DELETE {key}: {e}")
        
        return True

    def invalidate_pattern(self, pattern: str, cache_type: str = None) -> int:
        """
        Invalida chaves que correspondem ao padrão
        """
        count = 0
        
        # L1: Memória
        keys_to_remove = [k for k in self.memory_cache.keys() if self._matches_pattern(k, pattern)]
        for key in keys_to_remove:
            del self.memory_cache[key]
            count += 1
        
        # L2: Redis
        if self.redis_available:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
                    count += len(keys)
            except Exception as e:
                logger.error(f"❌ Erro no Redis INVALIDATE {pattern}: {e}")
        
        if count > 0:
            logger.info(f"🗑️ Cache invalidado: {count} chaves com padrão '{pattern}'")
        
        return count

    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Verifica se a chave corresponde ao padrão (simples)"""
        if '*' in pattern:
            parts = pattern.split('*')
            if len(parts) == 2:
                prefix, suffix = parts
                return key.startswith(prefix) and key.endswith(suffix)
        return key == pattern

    def get_stats(self) -> Dict:
        """Retorna estatísticas do cache"""
        stats = {
            'redis_available': self.redis_available,
            'memory_cache_size': len(self.memory_cache),
            'ttls': self.ttls
        }
        
        if self.redis_available:
            try:
                info = self.redis_client.info()
                stats.update({
                    'redis_memory_used': info.get('used_memory_human', 'N/A'),
                    'redis_connected_clients': info.get('connected_clients', 0),
                    'redis_total_commands': info.get('total_commands_processed', 0)
                })
            except:
                stats['redis_error'] = 'Could not fetch Redis stats'
        
        return stats

    def health_check(self) -> Dict[str, Any]:
        """Verifica saúde do sistema de cache"""
        health = {
            'memory_cache': 'ok',
            'redis_cache': 'unavailable'
        }
        
        if self.redis_available:
            try:
                self.redis_client.ping()
                health['redis_cache'] = 'ok'
            except:
                health['redis_cache'] = 'error'
                self.redis_available = False
        
        return health

    # MÉTODOS ESPECÍFICOS PARA LOOKUPS - NOVA FUNCIONALIDADE
    
    def get_all_lookups(self) -> Optional[Dict]:
        """
        Retorna todos os lookups (classificações, planos, itens) de uma vez
        """
        return self.get('lookups:all', 'lookups')
    
    def set_all_lookups(self, classificacoes: List[Dict], planos: List[Dict], itens: List[Dict]) -> bool:
        """
        Armazena todos os lookups de uma vez
        """
        lookups = {
            'classificacoes': {item['id']: item for item in classificacoes},
            'planos': {item['id']: item for item in planos}, 
            'itens': {item['id']: item for item in itens},
            'timestamp': datetime.now().isoformat()
        }
        
        return self.set('lookups:all', lookups, 'lookups')
    
    def get_classificacao_by_id(self, id_classificacao: int) -> Optional[Dict]:
        """
        Busca classificação específica do cache
        """
        lookups = self.get_all_lookups()
        if lookups and 'classificacoes' in lookups:
            return lookups['classificacoes'].get(str(id_classificacao))
        return None
    
    def get_plano_by_id(self, id_plano: int) -> Optional[Dict]:
        """
        Busca plano específico do cache
        """
        lookups = self.get_all_lookups()
        if lookups and 'planos' in lookups:
            return lookups['planos'].get(str(id_plano))
        return None
    
    def get_item_by_id(self, id_item: int) -> Optional[Dict]:
        """
        Busca item específico do cache  
        """
        lookups = self.get_all_lookups()
        if lookups and 'itens' in lookups:
            return lookups['itens'].get(str(id_item))
        return None

    def clear_lookups_cache(self):
        """
        Limpa cache de lookups quando dados estruturais mudarem
        """
        self.invalidate_pattern('lookups:*')

# Instância global
cache = CacheService()

# Decorator para cache automático
def cached(cache_type: str = 'default', key_func=None):
    """
    Decorator para cachear automaticamente resultados de funções
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Gera chave do cache
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Tenta buscar no cache
            result = cache.get(cache_key, cache_type)
            if result is not None:
                return result
            
            # Executa função e cacheia resultado
            result = await func(*args, **kwargs)
            cache.set(cache_key, result, cache_type)
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Gera chave do cache
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Tenta buscar no cache
            result = cache.get(cache_key, cache_type)
            if result is not None:
                return result
            
            # Executa função e cacheia resultado
            result = func(*args, **kwargs)
            cache.set(cache_key, result, cache_type)
            return result
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator