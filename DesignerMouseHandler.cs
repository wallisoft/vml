using System;
using System.Collections.Generic;
using System.Linq;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Primitives;
using Avalonia.Controls.Shapes;
using Avalonia.Input;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.VisualTree;

namespace VB;

/// <summary>
/// Handles all mouse interactions for the VML Designer including:
/// - Drag and drop
/// - Resize operations  
/// - Context menus
/// - Selection
/// </summary>
public static class DesignerMouseHandler
{
    // ========================================
    // DRAG STATE CLASS
    // ========================================
    public class DragState
    {
        public bool IsDragging { get; set; }
        public string? ResizeEdge { get; set; }
        public Point DragStart { get; set; }
        public double StartX { get; set; }
        public double StartY { get; set; }
        public double StartWidth { get; set; }
        public double StartHeight { get; set; }
    }

    // ========================================
    // CLIPBOARD SUPPORT
    // ========================================
    private static Control? copiedControl;
    private static bool isCutOperation;
    
    // ========================================
    // INITIALIZE MOUSE HANDLERS
    // ========================================
    public static void InitializeHandlers(Canvas designCanvas, Window mainWindow, TextBlock? statusText)
    {
        Control? activeControl = null;
        var activeState = new DragState();

        // LEFT CLICK - Select, drag, resize
        designCanvas.PointerPressed += (s, e) =>
        {
            var point = e.GetCurrentPoint(designCanvas);
            var canvasPos = point.Position;
            
            // Right click - context menu (check for VML menu first)
            if (point.Properties.IsRightButtonPressed)
            {
                var hit = designCanvas.InputHitTest(canvasPos);
                
                // Walk up visual tree to find canvas child
                Visual? element = hit as Visual;
                Control? canvasChild = null;
                
                while (element != null)
                {
                    if (element is Control ctrl && ctrl.Parent == designCanvas)
                    {
                        canvasChild = ctrl;
                        break;
                    }
                    element = element.GetVisualParent();
                }
                
                Console.WriteLine($"[RCLICK] Canvas child: {canvasChild?.GetType().Name} '{canvasChild?.Name}'");
                
                // Control clicked - show control menu
                if (canvasChild != null && canvasChild != designCanvas &&
                    canvasChild is not Rectangle && 
                    canvasChild.Name?.Contains("overlay") != true)
                {
                    VmlContextMenu.SetContextMenuTarget(canvasChild);
                    var controlMenu = VmlContextMenu.GetContextMenu("ControlContextMenu");
                    if (controlMenu != null)
                    {
                        controlMenu.Open(designCanvas);
                        e.Handled = true;
                        return;
                    }
                }
                
                // Canvas clicked - show canvas menu
                var canvasMenu = VmlContextMenu.GetContextMenu("CanvasContextMenu");
                if (canvasMenu != null)
                {
                    canvasMenu.Open(designCanvas);
                    e.Handled = true;
                }
                return;
            }

            // Left click - selection/drag/resize
            if (!point.Properties.IsLeftButtonPressed) return;
            
            // Find which control was clicked
            foreach (var child in designCanvas.Children.OfType<Control>()
                .Where(c => c != DesignerWindow.GetSelectionBorder() && c != DesignerWindow.GetDesignOverlay()))
            {
                var bounds = new Rect(Canvas.GetLeft(child), Canvas.GetTop(child), 
                    child.Bounds.Width, child.Bounds.Height);
                
                if (bounds.Contains(canvasPos))
                {
                    activeControl = child;
                    var localPos = new Point(canvasPos.X - bounds.X, canvasPos.Y - bounds.Y);
                    var zone = GetResizeZone(child, localPos);
                    
                    if (zone != null)
                    {
                        activeState.ResizeEdge = zone;
                        activeState.IsDragging = false;
                    }
                    else
                    {
                        activeState.IsDragging = true;
                        activeState.ResizeEdge = null;
                    }
                    
                    activeState.DragStart = canvasPos;
                    activeState.StartX = Canvas.GetLeft(child);
                    activeState.StartY = Canvas.GetTop(child);
                    activeState.StartWidth = child.Width; 
                    activeState.StartHeight = child.Height;   
                    
                    DesignerWindow.SelectControl(child);
                    e.Handled = true;
                    break;
                }
            }
        };

        // POINTER MOVED - Handle drag/resize and update status
        designCanvas.PointerMoved += (s, e) =>
        {
            var canvasPos = e.GetPosition(designCanvas);
            
            if (activeControl != null && activeState.ResizeEdge != null)
            {
                // Resize active
                HandleResize(activeControl, activeState.ResizeEdge, canvasPos, 
                    activeState.StartX, activeState.StartY, activeState.StartWidth, activeState.StartHeight);
                DesignerWindow.UpdateSelectionBorder();
            }
            else if (activeControl != null && activeState.IsDragging)
            {
                // Drag active
                var deltaX = canvasPos.X - activeState.DragStart.X;
                var deltaY = canvasPos.Y - activeState.DragStart.Y;
                Canvas.SetLeft(activeControl, activeState.StartX + deltaX);
                Canvas.SetTop(activeControl, activeState.StartY + deltaY);
                
                if (activeControl.Tag is Control real)
                {
                    Canvas.SetLeft(real, activeState.StartX + deltaX);
                    Canvas.SetTop(real, activeState.StartY + deltaY);
                }
                DesignerWindow.UpdateSelectionBorder();
            }
            else if (DesignerWindow.GetSelectedControl() != null)
            {
                var selectedControl = DesignerWindow.GetSelectedControl();
                // Hovering over selected control - show resize cursor
                var bounds = new Rect(Canvas.GetLeft(selectedControl), Canvas.GetTop(selectedControl),
                    selectedControl.Bounds.Width, selectedControl.Bounds.Height);
                
                if (bounds.Contains(canvasPos))
                {
                    var localPos = new Point(canvasPos.X - bounds.X, canvasPos.Y - bounds.Y);
                    var zone = GetResizeZone(selectedControl, localPos);
                    designCanvas.Cursor = GetCursorForZone(zone);
                }
                else
                {
                    designCanvas.Cursor = new Cursor(StandardCursorType.Arrow);
                }
            }
            
            // Update status bar
            var offsetX = (int)canvasPos.X - 150;
            var offsetY = (int)canvasPos.Y - 100;
            if (statusText != null && mainWindow != null)
            {
                var controlName = DesignerWindow.GetSelectedControl()?.Name ?? "None";
                var winW = (int)mainWindow.ClientSize.Width;
                var winH = (int)mainWindow.ClientSize.Height;
                statusText.Text = $"Selected: {controlName} | Window: {winW}x{winH} | Mouse: {offsetX},{offsetY}";
            }
        };

        // POINTER RELEASED - Save position/size changes
        designCanvas.PointerReleased += (s, e) =>
        {
            if (activeControl != null)
            {
                Console.WriteLine($"[MOUSE] Released - saving");
                
                if (activeControl.Tag is Control real)
                {
                    PropertyStore.Set(real.Name!, "X", Canvas.GetLeft(activeControl).ToString());
                    PropertyStore.Set(real.Name!, "Y", Canvas.GetTop(activeControl).ToString());
                    PropertyStore.Set(real.Name!, "Width", activeControl.Bounds.Width.ToString());
                    PropertyStore.Set(real.Name!, "Height", activeControl.Bounds.Height.ToString());
                }
                
                activeControl = null;
                activeState.IsDragging = false;
                activeState.ResizeEdge = null;
            }
        };
    }

    // ========================================
    // RESIZE ZONE DETECTION
    // ========================================
    private static string? GetResizeZone(Control control, Point pos)
    {
        const double edgeSize = 8;
        var w = control.Bounds.Width;
        var h = control.Bounds.Height;
        
        bool onLeft = pos.X <= edgeSize;
        bool onRight = pos.X >= w - edgeSize;
        bool onTop = pos.Y <= edgeSize;
        bool onBottom = pos.Y >= h - edgeSize;

        if (onTop && onLeft) return "NW";
        if (onTop && onRight) return "NE";
        if (onBottom && onLeft) return "SW";
        if (onBottom && onRight) return "SE";
        if (onTop) return "N";
        if (onBottom) return "S";
        if (onLeft) return "W";
        if (onRight) return "E";
        
        return null;
    }

    // ========================================
    // CURSOR FOR RESIZE ZONE
    // ========================================
    private static Cursor GetCursorForZone(string? zone)
    {
        return zone switch
        {
            "NW" or "SE" => new Cursor(StandardCursorType.TopLeftCorner),
            "NE" or "SW" => new Cursor(StandardCursorType.TopRightCorner),
            "N" or "S" => new Cursor(StandardCursorType.SizeNorthSouth),
            "W" or "E" => new Cursor(StandardCursorType.SizeWestEast),
            _ => new Cursor(StandardCursorType.Arrow)
        };
    }
    
    // ========================================
    // HANDLE RESIZE
    // ========================================
    private static void HandleResize(Control control, string edge, Point mousePos, double startX, double startY, double startWidth, double startHeight)
    {
        switch (edge)
        {
            case "E":
                control.Width = Math.Max(20, mousePos.X - startX);
                break;
            case "W":
                var newWidth = Math.Max(20, (startX + startWidth) - mousePos.X);
                Canvas.SetLeft(control, mousePos.X);
                control.Width = newWidth;
                break;
            case "S":
                control.Height = Math.Max(20, mousePos.Y - startY);
                break;
            case "N":
                var newHeight = Math.Max(20, (startY + startHeight) - mousePos.Y);
                Canvas.SetTop(control, mousePos.Y);
                control.Height = newHeight;
                break;
            case "NE":
                control.Width = Math.Max(20, mousePos.X - startX);
                var neHeight = Math.Max(20, (startY + startHeight) - mousePos.Y);
                Canvas.SetTop(control, mousePos.Y);
                control.Height = neHeight;
                break;
            case "NW":
                var nwWidth = Math.Max(20, (startX + startWidth) - mousePos.X);
                var nwHeight = Math.Max(20, (startY + startHeight) - mousePos.Y);
                Canvas.SetLeft(control, mousePos.X);
                Canvas.SetTop(control, mousePos.Y);
                control.Width = nwWidth;
                control.Height = nwHeight;
                break;
            case "SE":
                control.Width = Math.Max(20, mousePos.X - startX);
                control.Height = Math.Max(20, mousePos.Y - startY);
                break;
            case "SW":
                var swWidth = Math.Max(20, (startX + startWidth) - mousePos.X);
                Canvas.SetLeft(control, mousePos.X);
                control.Width = swWidth;
                control.Height = Math.Max(20, mousePos.Y - startY);
                break;
        }
        
        // Sync to real control if it exists
        if (control.Tag is Control real)
        {
            real.Width = control.Width;
            real.Height = control.Height;
            Canvas.SetLeft(real, Canvas.GetLeft(control));
            Canvas.SetTop(real, Canvas.GetTop(control));
        }
    }
}
