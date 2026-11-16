// Nous - janela propria do Nous no Windows (Nous.exe), com o motor do Edge embutido
// (WebView2, que ja' vem no Windows 11). So' mostra a janela: quem liga o Nous e' o
// launchers\start-nous.ps1 (via nous-hidden.vbs), lido ao vivo a cada abertura.
//
// Compilado na propria maquina por launchers\janela-nous.ps1 (csc.exe do .NET
// Framework 4.8 = C# 5: sem interpolacao de texto, sem ?. e sem nameof).
//
//   Nous.exe                  janela principal (uma so'; abrir de novo traz ela para a frente)
//   Nous.exe --sem-iniciar    idem, sem rodar o start-nous (quem chamou ja' esta ligando)
//   Nous.exe --code <url>     janela do Nous Code (http://127.0.0.1:8998/...)
//   Nous.exe --carregando     mostra a tela de carregamento sem conferir o servidor (teste)
//   Nous.exe --destino <url>  so' classifica o endereco (codigo de saida; usado nos testes)

using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

namespace Nous
{
    // para onde um endereco vai (o numero e' o codigo de saida do --destino)
    enum Destino { Nous = 0, NousCode = 1, Local = 2, Fora = 3, Bloqueado = 4 }

    static class Destinos
    {
        public const int PortaNous = 8080;
        public const int PortaCode = 8998;

        public static Destino Classificar(string endereco)
        {
            Uri u;
            if (string.IsNullOrEmpty(endereco) || !Uri.TryCreate(endereco, UriKind.Absolute, out u)) return Destino.Bloqueado;
            string s = u.Scheme.ToLowerInvariant();
            if (s == "mailto") return Destino.Fora;
            if (s == "about" || s == "blob" || s == "data") return Destino.Local;
            if (s == "file") return EhTelaDeCarregamento(u) ? Destino.Local : Destino.Bloqueado;
            if (s != "http" && s != "https") return Destino.Bloqueado;
            if (!EhLocal(u)) return Destino.Fora;
            if (u.Port == PortaNous) return Destino.Nous;
            if (u.Port == PortaCode) return Destino.NousCode;
            return Destino.Local;
        }

        // localhost, 127.x.x.x ou ::1 (nao "localhost.algum-site.com")
        static bool EhLocal(Uri u)
        {
            return u.IsLoopback && (u.HostNameType != UriHostNameType.Dns || u.Host.ToLowerInvariant() == "localhost");
        }

        static bool EhTelaDeCarregamento(Uri u)
        {
            try
            {
                string alvo = Path.GetFullPath(Caminhos.Carregamento);
                return string.Equals(Path.GetFullPath(u.LocalPath), alvo, StringComparison.OrdinalIgnoreCase);
            }
            catch { return false; }
        }
    }

    static class Caminhos
    {
        // janela\bin\Nous.exe -> pasta do app
        public static string App
        {
            get { return Path.GetFullPath(Path.Combine(Path.GetDirectoryName(Application.ExecutablePath), "..", "..")); }
        }
        public static string Carregamento { get { return Path.Combine(App, "launchers", "loading.html"); } }
        public static string Iniciar { get { return Path.Combine(App, "launchers", "nous-hidden.vbs"); } }
        public static string Dados
        {
            get
            {
                string d = Environment.GetEnvironmentVariable("DATA_DIR");
                if (string.IsNullOrEmpty(d)) d = Environment.GetEnvironmentVariable("NOUS_DATA_DIR");
                if (string.IsNullOrEmpty(d)) d = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "NousData");
                return d;
            }
        }
        public static string Pasta { get { return Path.Combine(Dados, "janela"); } }
    }

    static class Programa
    {
        public const string EnderecoNous = "http://localhost:8080";
        const string Mutex = "Local\\Nous.Janela.Principal";
        const string Sinal = "Local\\Nous.Janela.Mostrar";

        [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
        static extern int SetCurrentProcessExplicitAppUserModelID(string id);
        [DllImport("user32.dll")]
        static extern bool SetProcessDpiAwarenessContext(IntPtr valor);
        [DllImport("user32.dll")]
        static extern bool AllowSetForegroundWindow(int pid);

        [STAThread]
        static int Main(string[] args)
        {
            string destino = Valor(args, "--destino");
            if (destino != null) return (int)Destinos.Classificar(destino);

            try { SetProcessDpiAwarenessContext(new IntPtr(-4)); } catch { }   // nitido em tela com zoom
            try { SetCurrentProcessExplicitAppUserModelID("Nous.Janela"); } catch { }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string code = Valor(args, "--code");
            if (code != null)
            {
                if (Destinos.Classificar(code) != Destino.NousCode) return 4;
                Application.Run(new Janela(true, code, false, false));
                return 0;
            }

            bool primeiro;
            using (var trava = new Mutex(true, Mutex, out primeiro))
            {
                if (!primeiro)
                {
                    // ja' tem uma janela do Nous: traz ela para a frente e sai
                    try
                    {
                        AllowSetForegroundWindow(-1);
                        using (var ev = EventWaitHandle.OpenExisting(Sinal)) ev.Set();
                    }
                    catch { }
                    return 0;
                }
                using (var ev = new EventWaitHandle(false, EventResetMode.AutoReset, Sinal))
                {
                    var janela = new Janela(false, EnderecoNous, Tem(args, "--sem-iniciar"), Tem(args, "--carregando"));
                    var ouvinte = new Thread(() =>
                    {
                        while (ev.WaitOne())
                        {
                            try { janela.BeginInvoke(new Action(janela.Mostrar)); }
                            catch { if (janela.IsDisposed) break; }
                        }
                    });
                    ouvinte.IsBackground = true;
                    ouvinte.Start();
                    Application.Run(janela);
                }
            }
            return 0;
        }

        static bool Tem(string[] args, string nome)
        {
            foreach (var a in args) if (a == nome) return true;
            return false;
        }

        static string Valor(string[] args, string nome)
        {
            for (int i = 0; i < args.Length - 1; i++) if (args[i] == nome) return args[i + 1];
            return null;
        }
    }

    class Janela : Form
    {
        [DllImport("user32.dll")]
        static extern bool SetForegroundWindow(IntPtr janela);
        [DllImport("dwmapi.dll")]
        static extern int DwmSetWindowAttribute(IntPtr janela, int atributo, ref int valor, int tamanho);

        // A pagina avisa a cor do fundo (paleta, claro/escuro) e a barra de titulo segue.
        // Cores em oklch viram rgb por um canvas de 1 pixel.
        const string ScriptBarra =
            "(function(){if(window.top!==window||!window.chrome||!chrome.webview)return;var ult='';" +
            "function rgb(c){try{var x=document.createElement('canvas');x.width=x.height=1;var g=x.getContext('2d');" +
            "g.fillStyle='#000';g.fillStyle=c;g.fillRect(0,0,1,1);var d=g.getImageData(0,0,1,1).data;return d[0]+','+d[1]+','+d[2]}catch(e){return ''}}" +
            // a cor e' a do que aparece logo abaixo da barra, no meio da janela (o primeiro
            // fundo que nao e' transparente, subindo a partir do elemento ali)
            "function fundo(){var e=document.elementFromPoint(innerWidth/2,4);while(e){var b=getComputedStyle(e).backgroundColor;" +
            "if(b&&b!=='rgba(0, 0, 0, 0)'&&b!=='transparent')return b;e=e.parentElement}" +
            "return getComputedStyle(document.body).backgroundColor}" +
            "function ver(){if(!document.body)return;var c=fundo();" +
            "var k=rgb(c)+';'+(document.documentElement.classList.contains('dark')?1:0);if(k!==ult){ult=k;chrome.webview.postMessage('barra;'+k)}}" +
            // roda antes de a pagina existir (sem <html> ainda): o observador so' liga depois
            "function ligar(){try{new MutationObserver(ver).observe(document.documentElement,{attributes:true,attributeFilter:['class','data-nous-paleta','style']})}catch(e){}ver()}" +
            "if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ligar);else ligar();" +
            "addEventListener('load',ver);setInterval(ver,1500)})();";

        // diagnostico: com NOUS_JANELA_LOG=1, anota em NousData\janela\janela.log
        static void Anotar(string texto)
        {
            if (Environment.GetEnvironmentVariable("NOUS_JANELA_LOG") != "1") return;
            try { File.AppendAllText(Path.Combine(Caminhos.Pasta, "janela.log"), DateTime.Now.ToString("HH:mm:ss ") + texto + Environment.NewLine); } catch { }
        }

        void PintarBarra(string mensagem)
        {
            // "barra;R,G,B;escuro"
            Anotar("barra: " + mensagem);
            try
            {
                string[] p = mensagem.Split(';');
                string[] c = p[1].Split(',');
                int r = int.Parse(c[0]), g = int.Parse(c[1]), b = int.Parse(c[2]);
                int escuro = p.Length > 2 && p[2] == "1" ? 1 : 0;
                int cor = r | (g << 8) | (b << 16);                       // COLORREF = 0x00BBGGRR
                bool claro = (0.299 * r + 0.587 * g + 0.114 * b) > 150;
                int texto = claro ? 0x00141414 : 0x00F2F2F2;
                int a = DwmSetWindowAttribute(Handle, 20, ref escuro, 4);   // modo escuro da moldura
                int b2 = DwmSetWindowAttribute(Handle, 35, ref cor, 4);     // cor da barra (Windows 11)
                int c2 = DwmSetWindowAttribute(Handle, 36, ref texto, 4);   // cor do titulo
                Anotar("dwm: " + a + " " + b2 + " " + c2);
            }
            catch { }
        }

        readonly bool code;              // janela do Nous Code (pode haver varias)
        readonly string endereco;
        readonly bool semIniciar;
        readonly bool soCarregando;
        readonly WebView2 web;
        CoreWebView2Environment ambiente;
        System.Windows.Forms.Timer espera;   // confere o servidor enquanto mostra o carregamento
        static readonly Color Fundo = Color.FromArgb(20, 18, 16);

        public Janela(bool code, string endereco, bool semIniciar, bool soCarregando)
        {
            this.code = code;
            this.endereco = endereco;
            this.semIniciar = semIniciar;
            this.soCarregando = soCarregando;
            Text = code ? "Nous Code" : "Nous";
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
            BackColor = Fundo;
            MinimumSize = new Size(640, 480);
            web = new WebView2();
            web.Dock = DockStyle.Fill;
            web.DefaultBackgroundColor = Fundo;   // sem clarao branco antes da pagina
            Controls.Add(web);
            RestaurarPosicao();
            Load += delegate { Iniciar(); };
            FormClosing += delegate { GuardarPosicao(); };
        }

        public void Mostrar()
        {
            if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
            Show();
            Activate();
            BringToFront();
            SetForegroundWindow(Handle);
        }

        async void Iniciar()
        {
            try
            {
                Directory.CreateDirectory(Caminhos.Pasta);
                ambiente = await CoreWebView2Environment.CreateAsync(null, Path.Combine(Caminhos.Pasta, "perfil"));
                await web.EnsureCoreWebView2Async(ambiente);
            }
            catch (Exception ex)
            {
                // sem o WebView2: abre no navegador, como antes da janela propria
                MessageBox.Show("Não consegui abrir a janela do Nous (" + ex.Message + ").\n\nVou abrir no navegador.",
                    "Nous", MessageBoxButtons.OK, MessageBoxIcon.Information);
                AbrirFora(endereco);
                Close();
                return;
            }
            Anotar("webview pronto " + web.CoreWebView2.Environment.BrowserVersionString);
            Ligar(web.CoreWebView2);
            web.CoreWebView2.NavigationCompleted += (s, e) => Anotar("pagina: " + web.CoreWebView2.Source + " ok=" + e.IsSuccess);
            try { await web.CoreWebView2.AddScriptToExecuteOnDocumentCreatedAsync(ScriptBarra); }
            catch (Exception ex) { Anotar("script da barra: " + ex.Message); }
            web.CoreWebView2.WebMessageReceived += (s, e) =>
            {
                string m = null;
                try { m = e.TryGetWebMessageAsString(); } catch (Exception ex) { Anotar("mensagem: " + ex.Message); }
                Anotar("recebi: " + m);
                if (m != null && m.StartsWith("barra;")) PintarBarra(m);
            };
            web.CoreWebView2.ProcessFailed += (s, e) =>
            {
                if (e.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessExited ||
                    e.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessUnresponsive)
                {
                    try { web.CoreWebView2.Reload(); } catch { }
                }
            };

            if (code) { web.CoreWebView2.Navigate(endereco); return; }
            if (!soCarregando && await NoAr()) { web.CoreWebView2.Navigate(endereco); return; }

            // servidor fora do ar: tela de carregamento aqui dentro e, se ninguem estiver
            // ligando o Nous, liga (start-nous.ps1 sem abrir navegador nem outra janela)
            if (!semIniciar && !soCarregando) LigarNous();
            if (File.Exists(Caminhos.Carregamento)) web.CoreWebView2.Navigate(new Uri(Caminhos.Carregamento).AbsoluteUri);
            else web.CoreWebView2.NavigateToString("<html><body style=\"background:#141210;color:#ddd5c6;font:16px system-ui;" +
                "display:grid;place-items:center;height:100vh;margin:0\">Preparando o Nous…</body></html>");
            if (soCarregando) return;
            espera = new System.Windows.Forms.Timer();
            espera.Interval = 2000;
            espera.Tick += async (s, e) =>
            {
                espera.Stop();
                if (await NoAr())
                {
                    string agora = web.CoreWebView2.Source ?? "";
                    if (Destinos.Classificar(agora) != Destino.Nous) web.CoreWebView2.Navigate(endereco);
                    return;
                }
                espera.Start();
            };
            espera.Start();
        }

        // as regras de navegacao valem para a janela e para as janelas filhas
        void Ligar(CoreWebView2 c)
        {
            c.Settings.IsStatusBarEnabled = false;
            c.NavigationStarting += (s, e) =>
            {
                if (!e.IsUserInitiated && !e.IsRedirected && e.Uri.StartsWith("data:")) return;
                Destino d = Destinos.Classificar(e.Uri);
                if (d == Destino.Nous && !code) return;
                if (d == Destino.NousCode && code) return;
                if (d == Destino.Local) return;
                e.Cancel = true;
                Encaminhar(d, e.Uri);
            };
            c.NewWindowRequested += (s, e) =>
            {
                Destino d = Destinos.Classificar(e.Uri);
                if (d == Destino.Local) { AbrirFilha(e); return; }
                e.Handled = true;
                if (d == Destino.Nous && !code) { c.Navigate(e.Uri); return; }
                Encaminhar(d, e.Uri);
            };
            c.PermissionRequested += (s, e) =>
            {
                Destino d = Destinos.Classificar(e.Uri);
                bool doNous = d == Destino.Nous || d == Destino.NousCode || d == Destino.Local;
                if (doNous && (e.PermissionKind == CoreWebView2PermissionKind.Microphone ||
                               e.PermissionKind == CoreWebView2PermissionKind.ClipboardRead ||
                               e.PermissionKind == CoreWebView2PermissionKind.Notifications))
                    e.State = CoreWebView2PermissionState.Allow;
            };
        }

        void Encaminhar(Destino d, string uri)
        {
            Anotar("encaminhar " + d + ": " + uri);
            if (d == Destino.Fora) AbrirFora(uri);
            else if (d == Destino.NousCode) AbrirPrograma("--code \"" + uri + "\"");
            else if (d == Destino.Nous) AbrirPrograma("");          // janela principal (uma so')
            // Bloqueado: nao abre nada
        }

        static void AbrirFora(string uri)
        {
            try { Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true }); } catch { }
        }

        static void AbrirPrograma(string argumentos)
        {
            try { Process.Start(new ProcessStartInfo(Application.ExecutablePath, argumentos) { UseShellExecute = false }); } catch { }
        }

        // pagina local aberta em "nova janela" (relatorio de pesquisa, impressao...): janela
        // filha com o mesmo perfil, que o proprio WebView2 entrega pronta
        async void AbrirFilha(CoreWebView2NewWindowRequestedEventArgs e)
        {
            var adiado = e.GetDeferral();
            Anotar("janela filha: " + e.Uri);
            try
            {
                var f = new Form();
                f.Text = Text;
                f.Icon = Icon;
                f.BackColor = Fundo;
                f.Size = new Size(Math.Min(1200, Width), Math.Min(850, Height));
                f.StartPosition = FormStartPosition.CenterParent;
                var w = new WebView2();
                w.Dock = DockStyle.Fill;
                w.DefaultBackgroundColor = Fundo;
                f.Controls.Add(w);
                f.Show(this);
                await w.EnsureCoreWebView2Async(ambiente);
                Ligar(w.CoreWebView2);
                w.CoreWebView2.WindowCloseRequested += delegate { f.Close(); };
                w.CoreWebView2.DocumentTitleChanged += delegate { f.Text = w.CoreWebView2.DocumentTitle; };
                e.NewWindow = w.CoreWebView2;
                e.Handled = true;
            }
            catch { e.Handled = true; }
            finally { adiado.Complete(); }
        }

        void LigarNous()
        {
            try
            {
                var p = new ProcessStartInfo("wscript.exe", "\"" + Caminhos.Iniciar + "\"");
                p.UseShellExecute = false;
                p.CreateNoWindow = true;
                p.EnvironmentVariables["NOUS_SEM_NAVEGADOR"] = "1";
                Process.Start(p);
            }
            catch { }
        }

        static Task<bool> NoAr()
        {
            return Task.Run(() =>
            {
                try
                {
                    var r = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + Destinos.PortaNous + "/health");
                    r.Timeout = 2500;
                    r.Proxy = null;
                    using (var resp = (HttpWebResponse)r.GetResponse()) return resp.StatusCode == HttpStatusCode.OK;
                }
                catch { return false; }
            });
        }

        // ---------------------------------------------------------------- posicao
        string ArquivoPosicao { get { return Path.Combine(Caminhos.Pasta, code ? "code.txt" : "principal.txt"); } }

        void RestaurarPosicao()
        {
            Size = code ? new Size(1600, 1000) : new Size(1400, 900);
            StartPosition = FormStartPosition.CenterScreen;
            try
            {
                string[] p = File.ReadAllText(ArquivoPosicao).Trim().Split(';');
                var r = new Rectangle(int.Parse(p[0]), int.Parse(p[1]), int.Parse(p[2]), int.Parse(p[3]));
                bool visivel = false;
                foreach (var tela in Screen.AllScreens)
                    if (tela.WorkingArea.IntersectsWith(r) && r.Width >= 400 && r.Height >= 300) visivel = true;
                if (!visivel) return;   // monitor que nao existe mais: centraliza
                StartPosition = FormStartPosition.Manual;
                Bounds = r;
                if (p.Length > 4 && p[4] == "1") WindowState = FormWindowState.Maximized;
            }
            catch { }
        }

        void GuardarPosicao()
        {
            try
            {
                Rectangle r = WindowState == FormWindowState.Normal ? Bounds : RestoreBounds;
                Directory.CreateDirectory(Caminhos.Pasta);
                File.WriteAllText(ArquivoPosicao, string.Join(";", new string[] {
                    r.X.ToString(), r.Y.ToString(), r.Width.ToString(), r.Height.ToString(),
                    WindowState == FormWindowState.Maximized ? "1" : "0" }));
            }
            catch { }
        }
    }
}
