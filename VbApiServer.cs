using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Avalonia.Threading;

namespace VB;

/// <summary>
/// Rock-solid HTTP API server for VB Designer
/// Provides RESTful endpoints for control interaction and shell command execution
/// </summary>
public class VbApiServer
{
    private readonly MainWindow window;
    private readonly HttpListener listener;
    private readonly ApiControlHandler controlHandler;
    private bool isRunning;
    private readonly string apiKey;

    public VbApiServer(MainWindow mainWindow, string apiKey = "dev-1762055196")
    {
        this.window = mainWindow;
        this.apiKey = apiKey;
        this.listener = new HttpListener();
        this.controlHandler = new ApiControlHandler(mainWindow);
    }

    public void Start(int port = 8889)
    {
        if (isRunning) return;

        try
        {
            listener.Prefixes.Add($"http://+:{port}/");
            listener.Start();
            isRunning = true;

            Console.WriteLine($"[VB-API] Server started on port {port}");
            Console.WriteLine($"[VB-API] Endpoints:");
            Console.WriteLine($"[VB-API]   GET  /api/status");
            Console.WriteLine($"[VB-API]   GET  /api/controls");
            Console.WriteLine($"[VB-API]   GET  /api/controls/{{name}}");
            Console.WriteLine($"[VB-API]   POST /api/controls/{{name}}/set-property");
            Console.WriteLine($"[VB-API]   POST /api/controls/{{name}}/invoke-method");
            Console.WriteLine($"[VB-API]   POST /api/controls/{{name}}/fire-event");
            Console.WriteLine($"[VB-API]   POST /shell (timed execution)");

            // Start listening for requests
            Task.Run(HandleRequestsAsync);
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[VB-API] Failed to start: {ex.Message}");
        }
    }

    public void Stop()
    {
        if (!isRunning) return;

        isRunning = false;
        listener.Stop();
        listener.Close();
        Console.WriteLine("[VB-API] Server stopped");
    }

    private async Task HandleRequestsAsync()
    {
        while (isRunning)
        {
            try
            {
                var context = await listener.GetContextAsync();
                _ = Task.Run(() => ProcessRequestAsync(context));
            }
            catch (HttpListenerException)
            {
                // Listener was stopped
                break;
            }
            catch (Exception ex)
            {
                Console.WriteLine($"[VB-API] Error accepting request: {ex.Message}");
            }
        }
    }

    private async Task ProcessRequestAsync(HttpListenerContext context)
    {
        var request = context.Request;
        var response = context.Response;

        try
        {
            // Enable CORS for browser access
            response.Headers.Add("Access-Control-Allow-Origin", "*");
            response.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
            response.Headers.Add("Access-Control-Allow-Headers", "Content-Type, X-API-Key");

            if (request.HttpMethod == "OPTIONS")
            {
                response.StatusCode = 200;
                response.Close();
                return;
            }

            // Validate API key
            var requestKey = request.Headers["X-API-Key"];
            if (requestKey != apiKey)
            {
                await SendResponse(response, new { error = "Invalid API key" }, 401);
                return;
            }

            var path = request.Url?.AbsolutePath ?? "";
            var method = request.HttpMethod;

            Console.WriteLine($"[VB-API] {method} {path}");

            // Route the request
            if (path == "/api/status" && method == "GET")
            {
                await HandleStatus(response);
            }
            else if (path == "/api/controls" && method == "GET")
            {
                await HandleListControls(response);
            }
            else if (path.StartsWith("/api/controls/") && method == "GET")
            {
                var controlName = path.Substring("/api/controls/".Length);
                await HandleGetControl(response, controlName);
            }
            else if (path.StartsWith("/api/controls/") && path.EndsWith("/set-property") && method == "POST")
            {
                var controlName = path.Substring("/api/controls/".Length).Replace("/set-property", "");
                await HandleSetProperty(request, response, controlName);
            }
            else if (path.StartsWith("/api/controls/") && path.EndsWith("/invoke-method") && method == "POST")
            {
                var controlName = path.Substring("/api/controls/".Length).Replace("/invoke-method", "");
                await HandleInvokeMethod(request, response, controlName);
            }
            else if (path.StartsWith("/api/controls/") && path.EndsWith("/fire-event") && method == "POST")
            {
                var controlName = path.Substring("/api/controls/".Length).Replace("/fire-event", "");
                await HandleFireEvent(request, response, controlName);
            }
            else if (path == "/shell" && method == "POST")
            {
                await HandleShellCommand(request, response);
            }
            else
            {
                await SendResponse(response, new
                {
                    error = "Not found",
                    path = path,
                    available_endpoints = new[]
                    {
                        "GET  /api/status",
                        "GET  /api/controls",
                        "GET  /api/controls/{name}",
                        "POST /api/controls/{name}/set-property",
                        "POST /api/controls/{name}/invoke-method",
                        "POST /api/controls/{name}/fire-event",
                        "POST /shell"
                    }
                }, 404);
            }
        }
        catch (Exception ex)
        {
            Console.WriteLine($"[VB-API] Error processing request: {ex.Message}");
            await SendResponse(response, new { error = ex.Message }, 500);
        }
    }

    private async Task HandleStatus(HttpListenerResponse response)
    {
        await SendResponse(response, new
        {
            status = "ok",
            version = "1.0",
            port = 8889,
            timestamp = DateTime.UtcNow
        });
    }

    private async Task HandleListControls(HttpListenerResponse response)
    {
        var controls = await Dispatcher.UIThread.InvokeAsync(() => 
            controlHandler.GetAllControls()
        );

        await SendResponse(response, new
        {
            count = controls.Count,
            controls = controls
        });
    }

    private async Task HandleGetControl(HttpListenerResponse response, string controlName)
    {
        var control = await Dispatcher.UIThread.InvokeAsync(() => 
            controlHandler.GetControlInfo(controlName)
        );

        if (control == null)
        {
            await SendResponse(response, new { error = $"Control '{controlName}' not found" }, 404);
        }
        else
        {
            await SendResponse(response, control);
        }
    }

    private async Task HandleSetProperty(HttpListenerRequest request, HttpListenerResponse response, string controlName)
    {
        var body = await ReadRequestBody(request);
        var data = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);

        if (data == null || !data.ContainsKey("property") || !data.ContainsKey("value"))
        {
            await SendResponse(response, new { error = "Missing 'property' or 'value' in request body" }, 400);
            return;
        }

        var property = data["property"].GetString() ?? "";
        var value = data["value"].ToString();

        var result = await Dispatcher.UIThread.InvokeAsync(() => 
            controlHandler.SetProperty(controlName, property, value)
        );

        if (result.success)
        {
            await SendResponse(response, new { success = true, message = result.message });
        }
        else
        {
            await SendResponse(response, new { error = result.message }, 400);
        }
    }

    private async Task HandleInvokeMethod(HttpListenerRequest request, HttpListenerResponse response, string controlName)
    {
        var body = await ReadRequestBody(request);
        var data = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(body);

        if (data == null || !data.ContainsKey("method"))
        {
            await SendResponse(response, new { error = "Missing 'method' in request body" }, 400);
            return;
        }

        var method = data["method"].GetString() ?? "";
        var args = data.ContainsKey("args") ? 
            JsonSerializer.Deserialize<object[]>(data["args"].GetRawText()) : Array.Empty<object>();

        var result = await Dispatcher.UIThread.InvokeAsync(() => 
            controlHandler.InvokeMethod(controlName, method, args ?? Array.Empty<object>())
        );

        if (result.success)
        {
            await SendResponse(response, new { success = true, result = result.returnValue });
        }
        else
        {
            await SendResponse(response, new { error = result.message }, 400);
        }
    }

    private async Task HandleFireEvent(HttpListenerRequest request, HttpListenerResponse response, string controlName)
    {
        var body = await ReadRequestBody(request);
        var data = JsonSerializer.Deserialize<Dictionary<string, string>>(body);

        if (data == null || !data.ContainsKey("event"))
        {
            await SendResponse(response, new { error = "Missing 'event' in request body" }, 400);
            return;
        }

        var eventName = data["event"];

        var result = await Dispatcher.UIThread.InvokeAsync(() => 
            controlHandler.FireEvent(controlName, eventName)
        );

        if (result.success)
        {
            await SendResponse(response, new { success = true, message = result.message });
        }
        else
        {
            await SendResponse(response, new { error = result.message }, 400);
        }
    }

    private async Task HandleShellCommand(HttpListenerRequest request, HttpListenerResponse response)
    {
        var command = await ReadRequestBody(request);

        if (string.IsNullOrWhiteSpace(command))
        {
            await SendResponse(response, new { error = "Empty command" }, 400);
            return;
        }

        Console.WriteLine($"[VB-API] Executing shell command: {command}");

        var result = await ExecuteShellCommandAsync(command);

        await SendResponse(response, new
        {
            success = result.exitCode == 0,
            stdout = result.stdout,
            stderr = result.stderr,
            exit_code = result.exitCode,
            timed_out = result.timedOut
        });
    }

    private async Task<(string stdout, string stderr, int exitCode, bool timedOut)> ExecuteShellCommandAsync(string command)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = "/bin/bash",
            Arguments = $"-c \"{command.Replace("\"", "\\\"")}\"",
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true
        };

        using var process = new Process { StartInfo = startInfo };
        var stdout = new StringBuilder();
        var stderr = new StringBuilder();

        process.OutputDataReceived += (sender, e) =>
        {
            if (e.Data != null) stdout.AppendLine(e.Data);
        };

        process.ErrorDataReceived += (sender, e) =>
        {
            if (e.Data != null) stderr.AppendLine(e.Data);
        };

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        // Wait up to 60 seconds for command to complete
        var completed = await Task.Run(() => process.WaitForExit(60000));
        var timedOut = !completed;

        if (timedOut)
        {
            try
            {
                process.Kill(entireProcessTree: true);
                stderr.AppendLine("[TIMEOUT] Process killed after 60 seconds");
            }
            catch { }
        }

        return (stdout.ToString(), stderr.ToString(), timedOut ? -1 : process.ExitCode, timedOut);
    }

    private async Task<string> ReadRequestBody(HttpListenerRequest request)
    {
        using var reader = new StreamReader(request.InputStream, request.ContentEncoding);
        return await reader.ReadToEndAsync();
    }

    private async Task SendResponse(HttpListenerResponse response, object data, int statusCode = 200)
    {
        response.StatusCode = statusCode;
        response.ContentType = "application/json";

        var json = JsonSerializer.Serialize(data, new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = true
        });

        var buffer = Encoding.UTF8.GetBytes(json);
        response.ContentLength64 = buffer.Length;

        await response.OutputStream.WriteAsync(buffer, 0, buffer.Length);
        response.Close();
    }
}
