const s1 = document.getElementById('slider1');
const s2 = document.getElementById('slider2');
const v1 = document.getElementById('val1');
const v2 = document.getElementById('val2');
const st1 = document.getElementById('status1');
const st2 = document.getElementById('status2');
const linkado = document.getElementById('linkado');
const btnModo = document.getElementById('btn-modo');
const controles = document.getElementById('controles');
const badge = document.getElementById('badge-modo');

let timer1 = null, timer2 = null;
let modoAuto = false;

// ---------- Alternar modo ----------
function alternarModo() {
    modoAuto = !modoAuto;
    fetch('/set_modo?auto=' + (modoAuto ? '1' : '0'))
        .then(r => r.json())
        .then(d => {
            atualizarUIMode(d.modo_auto);
        })
        .catch(() => {
            modoAuto = !modoAuto; // reverte se falhar
        });
}

function atualizarUIMode(auto) {
    modoAuto = auto;
    if (auto) {
        btnModo.textContent = 'MODO AUTOMÁTICO';
        btnModo.classList.add('auto');
        badge.textContent = 'AUTO';
        badge.classList.add('auto');
        controles.classList.add('bloqueado');
    } else {
        btnModo.textContent = 'MODO MANUAL';
        btnModo.classList.remove('auto');
        badge.textContent = 'MANUAL';
        badge.classList.remove('auto');
        controles.classList.remove('bloqueado');
    }
}

// ---------- Sliders de potência ----------
s1.addEventListener('input', () => {
    v1.textContent = s1.value + '%';
    if (linkado.checked) { s2.value = s1.value; v2.textContent = s1.value + '%'; }
    st1.textContent = 'Aguardando...';
    clearTimeout(timer1);
    timer1 = setTimeout(() => {
        enviarPotencia(1, s1.value, st1);
        if (linkado.checked) enviarPotencia(2, s2.value, st2);
    }, 300);
});

s2.addEventListener('input', () => {
    v2.textContent = s2.value + '%';
    if (linkado.checked) { s1.value = s2.value; v1.textContent = s2.value + '%'; }
    st2.textContent = 'Aguardando...';
    clearTimeout(timer2);
    timer2 = setTimeout(() => {
        enviarPotencia(2, s2.value, st2);
        if (linkado.checked) enviarPotencia(1, s1.value, st1);
    }, 300);
});

function enviarPotencia(motor, val, statusEl) {
    statusEl.textContent = 'Enviando...';
    fetch(`/power?motor=${motor}&val=${val}`)
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(data => {
            statusEl.textContent = data.status === 'ok' ? `✓ ${val}%` : '✗ Erro';
        })
        .catch(() => { statusEl.textContent = '✗ Falha'; });
}

// ---------- Comandos manuais ----------
function mover(cmd) {
    if (modoAuto) return;
    fetch('/move?cmd=' + cmd)
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(() => atualizarLog())
        .catch(err => console.warn('Erro ao mover:', err));
}

// ---------- Log ----------
function atualizarLog() {
    fetch('/log')
        .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(data => {
            const d = document.getElementById('log');
            d.innerHTML = data.log.join('<br>');
            d.scrollTop = d.scrollHeight;
        })
        .catch(err => console.warn('Erro no log:', err));
}

setInterval(atualizarLog, 1000);

document.getElementById("btn-frente").addEventListener("click", () => mover("w"));
document.getElementById("btn-esq").addEventListener("click", () => mover("a"));
document.getElementById("btn-parar").addEventListener("click", () => mover("s"));
document.getElementById("btn-dir").addEventListener("click", () => mover("d"));
document.getElementById("btn-gire").addEventListener("click", () => mover("q"));
document.getElementById("btn-gird").addEventListener("click", () => mover("e"));