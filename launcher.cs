// Build with /target:winexe /platform:x64 /win32manifest:app.manifest.
// This launcher uses the Python installation already present on this computer.
using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Windows.Forms;

internal static class Launcher
{
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool SetDllDirectory(string folder);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibrary(string filename);
    [DllImport("kernel32.dll", CharSet = CharSet.Ansi, ExactSpelling = true)]
    private static extern IntPtr GetProcAddress(IntPtr module, string name);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate int PythonMain(int count, IntPtr arguments);

    private static int RunInProcess(string script, string[] args)
    {
        const string home = @"C:\Python313";
        SetDllDirectory(home);
        Environment.SetEnvironmentVariable("PYTHONHOME", home);
        IntPtr library = LoadLibrary(Path.Combine(home, "python313.dll"));
        if (library == IntPtr.Zero) throw new Exception("Unable to load Python 3.13.\n无法加载本机的 Python 3.13 运行环境。");
        IntPtr entry = GetProcAddress(library, "Py_Main");
        if (entry == IntPtr.Zero) throw new Exception("The Python entry point was not found.\nPython 运行环境缺少启动入口。");
        var pythonMain = (PythonMain)Marshal.GetDelegateForFunctionPointer(entry, typeof(PythonMain));
        var values = new string[args.Length + 2];
        values[0] = Path.Combine(home, "pythonw.exe");
        values[1] = script;
        Array.Copy(args, 0, values, 2, args.Length);
        var pointers = new IntPtr[values.Length];
        IntPtr array = Marshal.AllocHGlobal(IntPtr.Size * values.Length);
        try
        {
            for (int i = 0; i < values.Length; i++)
            {
                pointers[i] = Marshal.StringToHGlobalUni(values[i]);
                Marshal.WriteIntPtr(array, i * IntPtr.Size, pointers[i]);
            }
            return pythonMain(values.Length, array);
        }
        finally
        {
            foreach (IntPtr pointer in pointers)
                if (pointer != IntPtr.Zero) Marshal.FreeHGlobal(pointer);
            Marshal.FreeHGlobal(array);
        }
    }

    private static string Quote(string value)
    {
        var output = new StringBuilder("\"");
        int slashes = 0;
        foreach (char character in value)
        {
            if (character == '\\') { slashes++; continue; }
            if (character == '"')
            {
                output.Append('\\', slashes * 2 + 1).Append('"');
                slashes = 0;
                continue;
            }
            output.Append('\\', slashes).Append(character);
            slashes = 0;
        }
        return output.Append('\\', slashes * 2).Append('"').ToString();
    }

    private static string FindPython()
    {
        string[] candidates = {
            @"C:\Python313\pythonw.exe",
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "pyw.exe")
        };
        foreach (string candidate in candidates)
            if (File.Exists(candidate)) return candidate;
        foreach (string folder in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
        {
            try
            {
                foreach (string filename in new [] { "pyw.exe", "pythonw.exe" })
                {
                    string candidate = Path.Combine(folder.Trim().Trim('"'), filename);
                    if (File.Exists(candidate)) return candidate;
                }
            }
            catch (ArgumentException) { }
        }
        throw new FileNotFoundException("Install Python 3.10 or later with Tkinter.\n请安装带 Tkinter 的 Python 3.10 或以上版本。");
    }

    [STAThread]
    private static void Main(string[] args)
    {
        try
        {
            string folder = AppDomain.CurrentDomain.BaseDirectory;
            string script = Path.Combine(folder, "app.py");
            if (!File.Exists(script))
                throw new FileNotFoundException("Keep this launcher beside app.py and the other source files.\n请将启动程序与 app.py 等源文件放在同一文件夹。");
            if (File.Exists(@"C:\Python313\python313.dll"))
            {
                Environment.ExitCode = RunInProcess(script, args);
                return;
            }
            string python = FindPython();
            string arguments = (Path.GetFileName(python).Equals("pyw.exe", StringComparison.OrdinalIgnoreCase)
                ? "-3 " : "") + Quote(script);
            foreach (string argument in args) arguments += " " + Quote(argument);
            using (Process child = Process.Start(new ProcessStartInfo {
                FileName = python,
                Arguments = arguments,
                WorkingDirectory = folder,
                UseShellExecute = false,
                CreateNoWindow = true
            })) { child.WaitForExit(); Environment.ExitCode = child.ExitCode; }
        }
        catch (Exception error)
        {
            MessageBox.Show(error.Message, "Problem Review / 题目复习助手", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
