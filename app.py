#!/usr/bin/env python3
"""
Sistema Ótica - API Simplificada para Deploy
Versão otimizada para Render.com
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import hashlib
import jwt
import os
from datetime import datetime, timedelta

# Configurações de ambiente
SECRET_KEY = os.getenv("SECRET_KEY", "optica-secret-key-2026")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./optica.db")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")

# Extrair caminho do banco SQLite
DB_PATH = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")

# App
app = FastAPI(
    title="Sistema Ótica - API",
    description="API completa para gestão de óticas e joalherias",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== MODELS ====================

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    token: str
    usuario: dict
    empresa: dict

# ==================== DATABASE ====================

def get_db():
    """Conecta ao banco de dados"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"❌ Erro ao conectar banco: {e}")
        # Se não existir, criar banco básico
        criar_banco_basico()
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def criar_banco_basico():
    """Cria estrutura básica do banco se não existir"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabela empresas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS empresas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cnpj TEXT,
            email TEXT,
            telefone TEXT,
            ativo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tabela usuarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            empresa_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            senha_hash TEXT NOT NULL,
            funcao TEXT DEFAULT 'vendedor',
            ativo INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (empresa_id) REFERENCES empresas(id)
        )
    """)
    
    # Inserir empresa de teste se não existir
    cursor.execute("SELECT COUNT(*) FROM empresas")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO empresas (nome, cnpj, email, telefone)
            VALUES ('Ótica Vision', '12.345.678/0001-90', 'contato@oticavision.com.br', '(11) 98765-4321')
        """)
        
        # Senha hash de "123456"
        senha_hash = hashlib.sha256("123456".encode()).hexdigest()
        cursor.execute("""
            INSERT INTO usuarios (empresa_id, nome, email, senha_hash, funcao)
            VALUES (1, 'Administrador', 'admin@oticavision.com.br', ?, 'admin')
        """, (senha_hash,))
    
    conn.commit()
    conn.close()
    print("✅ Banco de dados básico criado com sucesso!")

# ==================== ENDPOINTS ====================

@app.get("/")
def root():
    """Endpoint raiz"""
    return {
        "sistema": "Sistema Ótica - API",
        "versao": "1.0.0",
        "status": "online",
        "documentacao": "/docs",
        "ambiente": ENVIRONMENT
    }

@app.get("/api/status")
def status():
    """Status do sistema"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Contar tabelas
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        total_tabelas = cursor.fetchone()[0]
        
        # Contar empresas
        cursor.execute("SELECT COUNT(*) FROM empresas WHERE ativo = 1")
        total_empresas = cursor.fetchone()[0]
        
        # Contar usuários
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE ativo = 1")
        total_usuarios = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "status": "ok",
            "database": True,
            "ambiente": ENVIRONMENT,
            "tabelas": total_tabelas,
            "empresas_ativas": total_empresas,
            "usuarios_ativos": total_usuarios,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "database": False,
            "erro": str(e),
            "timestamp": datetime.now().isoformat()
        }

@app.post("/api/login", response_model=LoginResponse)
def login(request: LoginRequest):
    """Login de usuário"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Hash da senha
        senha_hash = hashlib.sha256(request.password.encode()).hexdigest()
        
        # Buscar usuário
        cursor.execute("""
            SELECT u.*, e.nome as empresa_nome, e.cnpj
            FROM usuarios u
            JOIN empresas e ON u.empresa_id = e.id
            WHERE u.email = ? AND u.senha_hash = ? AND u.ativo = 1
        """, (request.email, senha_hash))
        
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        
        usuario = dict(row)
        
        # Gerar token JWT
        token_data = {
            "user_id": usuario["id"],
            "empresa_id": usuario["empresa_id"],
            "email": usuario["email"],
            "funcao": usuario["funcao"],
            "exp": datetime.utcnow() + timedelta(days=7)
        }
        token = jwt.encode(token_data, SECRET_KEY, algorithm="HS256")
        
        conn.close()
        
        return LoginResponse(
            token=token,
            usuario={
                "id": usuario["id"],
                "nome": usuario["nome"],
                "email": usuario["email"],
                "funcao": usuario["funcao"]
            },
            empresa={
                "id": usuario["empresa_id"],
                "nome": usuario["empresa_nome"],
                "cnpj": usuario["cnpj"]
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro no login: {str(e)}")

@app.get("/api/usuarios")
def listar_usuarios():
    """Lista todos os usuários"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT u.id, u.nome, u.email, u.funcao, u.ativo,
                   e.nome as empresa_nome
            FROM usuarios u
            JOIN empresas e ON u.empresa_id = e.id
            ORDER BY u.nome
        """)
        
        usuarios = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return {
            "total": len(usuarios),
            "usuarios": usuarios
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/empresas")
def listar_empresas():
    """Lista todas as empresas"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM empresas ORDER BY nome")
        empresas = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {
            "total": len(empresas),
            "empresas": empresas
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    """Health check para monitoramento"""
    return {"status": "healthy"}

# ==================== STARTUP ====================

@app.on_event("startup")
def startup_event():
    """Executado ao iniciar a aplicação"""
    print("=" * 60)
    print("🚀 Sistema Ótica - Iniciando...")
    print(f"📦 Ambiente: {ENVIRONMENT}")
    print(f"🗄️  Banco de dados: {DB_PATH}")
    print("=" * 60)
    
    # Garantir que banco existe
    try:
        conn = get_db()
        conn.close()
        print("✅ Banco de dados conectado com sucesso!")
    except Exception as e:
        print(f"⚠️  Aviso: {e}")
        print("🔧 Criando banco de dados...")
        criar_banco_basico()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)
