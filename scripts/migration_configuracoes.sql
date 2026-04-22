-- Migration: tabela de configurações dinâmicas do portal
-- Permite alterar credenciais e settings via portal admin sem editar .env

CREATE TABLE IF NOT EXISTS configuracoes (
    id             SERIAL PRIMARY KEY,
    chave          VARCHAR(100) UNIQUE NOT NULL,
    valor          TEXT,
    sensivel       BOOLEAN DEFAULT FALSE,
    descricao      VARCHAR(255),
    atualizado_em  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_configuracoes_chave ON configuracoes(chave);

-- Valores iniciais — não sobrescreve se já existir
INSERT INTO configuracoes (chave, valor, sensivel, descricao) VALUES
    ('gmail_user',               '',               false, 'Conta Gmail para envio de e-mails'),
    ('gmail_app_password',       '',               true,  'Senha de app Gmail (16 caracteres)'),
    ('email_remetente_nome',     'Effective Gain', false, 'Nome exibido nos e-mails enviados'),
    ('smtp_host',                'smtp.gmail.com', false, 'Servidor SMTP'),
    ('smtp_port',                '587',            false, 'Porta SMTP'),
    ('evolution_instance',       '',               false, 'Nome da instância Evolution API'),
    ('briefing_numero_destino',  '',               false, 'Número WhatsApp para o briefing matinal'),
    ('briefing_hora',            '08:00',          false, 'Horário do briefing (HH:MM)'),
    ('briefing_ativo',           'true',           false, 'Briefing matinal ativo (true/false)'),
    ('webhook_secret',           '',               true,  'Chave secreta do webhook Evolution API')
ON CONFLICT (chave) DO NOTHING;
