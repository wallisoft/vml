using System.Collections.Generic;

namespace VB;

public class VmlControl
{
    public string Type { get; set; } = "";
    public string? Name { get; set; }
    public Dictionary<string, string> Properties { get; set; } = new();
    public List<VmlControl> Children { get; set; } = new();
}
