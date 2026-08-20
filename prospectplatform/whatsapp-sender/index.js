const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, delay, WASocket } = require('@whiskeysockets/baileys');
const express = require('express');
const pino = require('pino');
const qrcode = require('qrcode-terminal');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3100;
const SESSION_DIR = path.join(__dirname, 'session');
const LOG_FILE = path.join(__dirname, 'sender.log');

let sock = null;
let connectionStatus = 'disconnected';
let lastQr = null;
let messageQueue = [];
let isProcessing = false;
let stats = { sent: 0, failed: 0, lastSentAt: null };

function log(level, msg, data = {}) {
    const entry = JSON.stringify({ ts: new Date().toISOString(), level, msg, ...data });
    fs.appendFileSync(LOG_FILE, entry + '\n');
    if (level === 'error') console.error(`[ERROR] ${msg}`, data);
}

async function startSock() {
    const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);

    sock = makeWASocket({
        auth: state,
        printQRInTerminal: false,
        logger: pino({ level: 'silent' }),
        browser: ['ProspectPlatform', 'Chrome', '1.0.0'],
        markOnlineOnConnect: false,
    });

    sock.ev.on('creds.update', saveCreds);

    sock.ev.on('connection.update', (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            lastQr = qr;
            connectionStatus = 'waiting_qr';
            log('info', 'QR code recebido');
            qrcode.generate(qr, { small: true });
        }

        if (connection === 'close') {
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== DisconnectReason.loggedOut;
            log('info', `Conexao fechada. Status: ${statusCode}. Reconectar: ${shouldReconnect}`);
            connectionStatus = 'disconnected';
            sock = null;

            if (shouldReconnect) {
                setTimeout(startSock, 5000);
            }
        }

        if (connection === 'open') {
            connectionStatus = 'connected';
            lastQr = null;
            log('info', 'Conectado ao WhatsApp');
        }
    });

    sock.ev.on('messages.upsert', ({ messages }) => {
        // Ignorar mensagens próprias
    });
}

function isValidPhoneNumber(phone) {
    const cleaned = phone.replace(/\D/g, '');
    return cleaned.length >= 10 && cleaned.length <= 15;
}

function formatPhoneForJid(phone) {
    const cleaned = phone.replace(/\D/g, '');
    return cleaned + '@s.whatsapp.net';
}

async function sendMessage(phone, message, options = {}) {
    if (connectionStatus !== 'connected') {
        throw new Error('WhatsApp nao conectado');
    }

    if (!isValidPhoneNumber(phone)) {
        throw new Error(`Telefone invalido: ${phone}`);
    }

    const jid = formatPhoneForJid(phone);

    // Simular "digitando..."
    if (options.simulateTyping !== false) {
        await sock.presenceUpdate(jid, 'composing');
        await delay(1000 + Math.random() * 2000);
        await sock.presenceUpdate(jid, 'paused');
    }

    // Delay aleatório antes de enviar
    const extraDelay = (options.extraDelay || 500) + Math.random() * 1000;
    await delay(extraDelay);

    const result = await sock.sendMessage(jid, { text: message });

    stats.sent++;
    stats.lastSentAt = new Date().toISOString();

    log('info', 'Mensagem enviada', { phone, messageId: result.key.id });

    return {
        success: true,
        messageId: result.key.id,
        timestamp: result.messageTimestamp,
    };
}

// --- Endpoints ---

app.get('/status', (req, res) => {
    res.json({
        connected: connectionStatus === 'connected',
        connectionStatus,
        hasQr: !!lastQr,
        stats,
        uptime: process.uptime(),
    });
});

app.get('/qr', (req, res) => {
    if (!lastQr) {
        return res.json({ qr: null, message: 'Nenhum QR pendente. Status: ' + connectionStatus });
    }
    res.json({ qr: lastQr });
});

app.post('/send', async (req, res) => {
    try {
        const { phone, message, extraDelay, simulateTyping } = req.body;

        if (!phone || !message) {
            return res.status(400).json({ error: 'phone e message sao obrigatorios' });
        }

        if (connectionStatus !== 'connected') {
            return res.status(503).json({ error: 'WhatsApp nao conectado', connectionStatus });
        }

        const result = await sendMessage(phone, message, { extraDelay, simulateTyping });
        res.json(result);
    } catch (e) {
        stats.failed++;
        log('error', 'Erro ao enviar', { error: e.message, phone: req.body.phone });
        res.status(500).json({ error: e.message });
    }
});

app.post('/pause', (req, res) => {
    connectionStatus = 'paused';
    log('info', 'Envios pausados via endpoint');
    res.json({ status: 'paused' });
});

app.post('/resume', (req, res) => {
    if (connectionStatus === 'paused') {
        connectionStatus = 'connected';
        log('info', 'Envios retomados via endpoint');
    }
    res.json({ status: connectionStatus });
});

app.post('/logout', async (req, res) => {
    try {
        if (sock) {
            await sock.logout();
        }
        if (fs.existsSync(SESSION_DIR)) {
            fs.rmSync(SESSION_DIR, { recursive: true, force: true });
        }
        connectionStatus = 'disconnected';
        log('info', 'Sessao encerrada');
        res.json({ status: 'logged_out' });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

startSock().catch(e => log('error', 'Erro ao iniciar', { error: e.message }));

app.listen(PORT, () => {
    log('info', `Servidor iniciado na porta ${PORT}`);
    console.log(`WhatsApp Sender rodando em http://localhost:${PORT}`);
});
