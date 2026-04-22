-- ============================================================
-- Integrador EG — Schema do produto
-- Executar: psql $DATABASE_URL < scripts/migration.sql
-- ============================================================

-- Clientes (projetos / empresas atendidas pela EG)
CREATE TABLE IF NOT EXISTS clientes (
    id              SERIAL PRIMARY KEY,
    nome            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) UNIQUE NOT NULL,
    whatsapp_grupo  VARCHAR(100),
    plano           VARCHAR(50)  NOT NULL DEFAULT 'premium',
    ativo           BOOLEAN      NOT NULL DEFAULT TRUE,
    criado_em       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Usuários (admins EG + representantes de clientes)
CREATE TABLE IF NOT EXISTS usuarios (
    id          SERIAL PRIMARY KEY,
    email       VARCHAR(255) UNIQUE NOT NULL,
    nome        VARCHAR(255) NOT NULL,
    senha_hash  VARCHAR(255) NOT NULL,
    papel       VARCHAR(20)  NOT NULL DEFAULT 'cliente',
    cliente_id  INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
    criado_em   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Adicionar colunas caso a tabela usuarios já exista sem elas
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'usuarios' AND column_name = 'papel'
    ) THEN
        ALTER TABLE usuarios ADD COLUMN papel VARCHAR(20) NOT NULL DEFAULT 'cliente';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'usuarios' AND column_name = 'cliente_id'
    ) THEN
        ALTER TABLE usuarios
            ADD COLUMN cliente_id INTEGER REFERENCES clientes(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'usuarios' AND column_name = 'criado_em'
    ) THEN
        ALTER TABLE usuarios ADD COLUMN criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- Execuções (cada ação disparada via WhatsApp)
CREATE TABLE IF NOT EXISTS execucoes (
    id              SERIAL PRIMARY KEY,
    cliente_id      INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
    grupo_id        VARCHAR(100),
    grupo_nome      VARCHAR(255),
    remetente       VARCHAR(100),
    acao            VARCHAR(50),
    projeto         VARCHAR(100),
    conteudo_resumo TEXT,
    resultado       VARCHAR(20)  NOT NULL DEFAULT 'sucesso',
    erro_detalhe    TEXT,
    criado_em       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Receitas ativas (automações configuradas por cliente)
CREATE TABLE IF NOT EXISTS receitas_ativas (
    id              SERIAL PRIMARY KEY,
    cliente_id      INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
    nome            VARCHAR(255) NOT NULL,
    descricao       TEXT,
    gatilho         VARCHAR(255),
    sistema_destino VARCHAR(100),
    status          VARCHAR(20)  NOT NULL DEFAULT 'ativa',
    ultima_execucao TIMESTAMPTZ,
    total_execucoes INTEGER      NOT NULL DEFAULT 0,
    criado_em       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- Briefings enviados (histórico)
CREATE TABLE IF NOT EXISTS briefings_enviados (
    id              SERIAL PRIMARY KEY,
    cliente_id      INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
    data_referencia DATE         NOT NULL,
    conteudo        TEXT,
    numero_destino  VARCHAR(20),
    enviado_em      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    sucesso         BOOLEAN      NOT NULL DEFAULT TRUE
);

-- Dead letter (falhas de integração Obsidian — pode já existir)
CREATE TABLE IF NOT EXISTS dead_letter (
    id               SERIAL PRIMARY KEY,
    grupo            VARCHAR(100),
    projeto          VARCHAR(100),
    acao             VARCHAR(50),
    conteudo         TEXT,
    erro_original    TEXT,
    tentativas       INTEGER      NOT NULL DEFAULT 0,
    resolvido        BOOLEAN      NOT NULL DEFAULT FALSE,
    criado_em        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ultima_tentativa TIMESTAMPTZ
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_execucoes_cliente    ON execucoes(cliente_id);
CREATE INDEX IF NOT EXISTS idx_execucoes_criado_em  ON execucoes(criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_execucoes_grupo      ON execucoes(grupo_nome);
CREATE INDEX IF NOT EXISTS idx_execucoes_acao       ON execucoes(acao);
CREATE INDEX IF NOT EXISTS idx_receitas_cliente     ON receitas_ativas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_briefings_cliente    ON briefings_enviados(cliente_id);
CREATE INDEX IF NOT EXISTS idx_briefings_data       ON briefings_enviados(data_referencia DESC);
