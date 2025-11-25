using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Avalonia;
using Avalonia.Controls;
using Avalonia.VisualTree;

namespace VB;

/// <summary>
/// Handles control interaction via reflection
/// Provides property get/set, method invocation, and event firing
/// </summary>
public class ApiControlHandler
{
    private readonly MainWindow window;

    public ApiControlHandler(MainWindow mainWindow)
    {
        this.window = mainWindow;
        Console.WriteLine("[API] Control handler initialized");
    }

    /// <summary>
    /// Get all controls in the visual tree
    /// </summary>
    public List<object> GetAllControls()
    {
        var controls = new List<object>();

        void TraverseTree(Visual? visual, string path = "")
        {
            if (visual == null) return;

            if (visual is Control control)
            {
                var name = control.Name ?? control.GetType().Name;
                var fullPath = string.IsNullOrEmpty(path) ? name : $"{path}/{name}";

                controls.Add(new
                {
                    name = control.Name ?? "(unnamed)",
                    type = control.GetType().Name,
                    path = fullPath,
                    bounds = new
                    {
                        x = control.Bounds.X,
                        y = control.Bounds.Y,
                        width = control.Bounds.Width,
                        height = control.Bounds.Height
                    }
                });

                foreach (var child in visual.GetVisualChildren())
                {
                    TraverseTree(child, fullPath);
                }
            }
            else
            {
                foreach (var child in visual.GetVisualChildren())
                {
                    TraverseTree(child, path);
                }
            }
        }

        TraverseTree(window);
        return controls;
    }

    /// <summary>
    /// Get detailed information about a specific control
    /// </summary>
    public object? GetControlInfo(string controlName)
    {
        var control = FindControl(controlName);
        if (control == null) return null;

        var type = control.GetType();
        var properties = type.GetProperties(BindingFlags.Public | BindingFlags.Instance)
            .Where(p => p.CanRead)
            .Select(p =>
            {
                try
                {
                    var value = p.GetValue(control);
                    return new
                    {
                        name = p.Name,
                        type = p.PropertyType.Name,
                        value = value?.ToString() ?? "null",
                        writable = p.CanWrite
                    };
                }
                catch
                {
                    return new
                    {
                        name = p.Name,
                        type = p.PropertyType.Name,
                        value = "(error reading)",
                        writable = p.CanWrite
                    };
                }
            })
            .ToList();

        var methods = type.GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => !m.IsSpecialName) // Exclude property accessors
            .Select(m => new
            {
                name = m.Name,
                returnType = m.ReturnType.Name,
                parameters = m.GetParameters().Select(p => new
                {
                    name = p.Name,
                    type = p.ParameterType.Name
                }).ToArray()
            })
            .ToList();

        var events = type.GetEvents(BindingFlags.Public | BindingFlags.Instance)
            .Select(e => new
            {
                name = e.Name,
                type = e.EventHandlerType?.Name ?? "unknown"
            })
            .ToList();

        return new
        {
            name = control.Name ?? "(unnamed)",
            type = type.Name,
            fullTypeName = type.FullName,
            bounds = new
            {
                x = control.Bounds.X,
                y = control.Bounds.Y,
                width = control.Bounds.Width,
                height = control.Bounds.Height
            },
            properties = properties,
            methods = methods,
            events = events
        };
    }

    /// <summary>
    /// Set a property on a control
    /// </summary>
    public (bool success, string message) SetProperty(string controlName, string propertyName, string value)
    {
        var control = FindControl(controlName);
        if (control == null)
            return (false, $"Control '{controlName}' not found");

        var property = control.GetType().GetProperty(propertyName, BindingFlags.Public | BindingFlags.Instance);
        if (property == null)
            return (false, $"Property '{propertyName}' not found on {control.GetType().Name}");

        if (!property.CanWrite)
            return (false, $"Property '{propertyName}' is read-only");

        try
        {
            var convertedValue = ConvertValue(value, property.PropertyType);
            property.SetValue(control, convertedValue);
            Console.WriteLine($"[API] Set {controlName}.{propertyName} = {value}");
            return (true, $"Property '{propertyName}' set to '{value}'");
        }
        catch (Exception ex)
        {
            return (false, $"Error setting property: {ex.Message}");
        }
    }

    /// <summary>
    /// Invoke a method on a control
    /// </summary>
    public (bool success, string message, object? returnValue) InvokeMethod(string controlName, string methodName, object[] args)
    {
        var control = FindControl(controlName);
        if (control == null)
            return (false, $"Control '{controlName}' not found", null);

        var method = control.GetType().GetMethod(methodName, BindingFlags.Public | BindingFlags.Instance);
        if (method == null)
            return (false, $"Method '{methodName}' not found on {control.GetType().Name}", null);

        try
        {
            // Convert arguments to proper types
            var parameters = method.GetParameters();
            var convertedArgs = new object?[parameters.Length];

            for (int i = 0; i < parameters.Length && i < args.Length; i++)
            {
                convertedArgs[i] = ConvertValue(args[i]?.ToString() ?? "", parameters[i].ParameterType);
            }

            var result = method.Invoke(control, convertedArgs);
            Console.WriteLine($"[API] Invoked {controlName}.{methodName}()");
            return (true, $"Method '{methodName}' invoked successfully", result);
        }
        catch (Exception ex)
        {
            return (false, $"Error invoking method: {ex.Message}", null);
        }
    }

    /// <summary>
    /// Fire an event on a control (simulate event trigger)
    /// </summary>
    public (bool success, string message) FireEvent(string controlName, string eventName)
    {
        var control = FindControl(controlName);
        if (control == null)
            return (false, $"Control '{controlName}' not found");

        var eventInfo = control.GetType().GetEvent(eventName, BindingFlags.Public | BindingFlags.Instance);
        if (eventInfo == null)
            return (false, $"Event '{eventName}' not found on {control.GetType().Name}");

        try
        {
            // For common events, we can simulate them
            if (eventName == "Click" && control is Button button)
            {
                // Simulate button click by finding and invoking the command or click handler
                var clickMethod = typeof(Button).GetMethod("OnClick", BindingFlags.NonPublic | BindingFlags.Instance);
                if (clickMethod != null)
                {
                    clickMethod.Invoke(button, null);
                    Console.WriteLine($"[API] Fired {controlName}.{eventName}");
                    return (true, $"Event '{eventName}' fired on button");
                }
            }

            // For other events, we'd need to raise them properly
            // This is complex and event-specific
            return (false, $"Cannot automatically fire event '{eventName}' - not implemented for this control type");
        }
        catch (Exception ex)
        {
            return (false, $"Error firing event: {ex.Message}");
        }
    }

    /// <summary>
    /// Find a control by name in the visual tree
    /// </summary>
    private Control? FindControl(string name)
    {
        Control? found = null;

        void SearchTree(Visual? visual)
        {
            if (visual == null || found != null) return;

            if (visual is Control control && control.Name == name)
            {
                found = control;
                return;
            }

            foreach (var child in visual.GetVisualChildren())
            {
                SearchTree(child);
            }
        }

        // First check if it's the main window itself
        if (window.Name == name)
            return window;

        SearchTree(window);
        return found;
    }

    /// <summary>
    /// Convert string value to target type using reflection
    /// </summary>
    private object? ConvertValue(string value, Type targetType)
    {
        if (targetType == typeof(string))
            return value;

        if (targetType == typeof(int))
            return int.Parse(value);

        if (targetType == typeof(double))
            return double.Parse(value);

        if (targetType == typeof(bool))
            return bool.Parse(value);

        if (targetType == typeof(float))
            return float.Parse(value);

        if (targetType == typeof(long))
            return long.Parse(value);

        if (targetType.IsEnum)
            return Enum.Parse(targetType, value);

        // For complex types, try to use TypeConverter or JSON deserialization
        try
        {
            var converter = System.ComponentModel.TypeDescriptor.GetConverter(targetType);
            if (converter.CanConvertFrom(typeof(string)))
                return converter.ConvertFromString(value);
        }
        catch { }

        throw new InvalidOperationException($"Cannot convert '{value}' to type {targetType.Name}");
    }
}
