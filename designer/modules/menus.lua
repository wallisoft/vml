-- The Visualised designer: the menu bar of the form being designed.
-- One of the modules of designer/Designer.vmlproj. Each function here is a handler: a control or menu item of the
-- designer names it (OnClick=FileSave), or another handler runs it with Vml("RunScript", "FileSave").

function ShowMenuItemMenu(...)
    -- the bar's empty space has its own menu; items have theirs
    if Vml("GetProperty", "Surface", "Selected") == "menubar" then
        Vml("ShowContextMenu", "MenuBarMenu")
    else
        Vml("ShowContextMenu", "MenuItemMenu")
    end
end

function MenuBarAdd(...)
    Vml("MenuAddItem", "menubar", "end")
end

function MenuBarRemove(...)
    if Vml("ConfirmDialog", "Remove the whole menu bar and its scripts?", "Menu") == "true" then
        Vml("SetDesignMenu", "Surface", "[]")
        Vml("SetProperty", "Surface", "Selected", "")
        Vml("RunScript", "SelectionChanged")
    end
end

function AddMenu(...)
    Vml("MenuAddItem", "", "first")
end

function MenuAddBefore(...)
    Vml("MenuAddItem", Vml("GetProperty", "Surface", "Selected"), "before")
end

function MenuAddAfter(...)
    Vml("MenuAddItem", Vml("GetProperty", "Surface", "Selected"), "after")
end

function MenuAddChild(...)
    Vml("MenuAddItem", Vml("GetProperty", "Surface", "Selected"), "child")
end

function OpenMenuEditor(...)
    -- the Menu Editor is a VML form too
    Vml("FormOpenModal", "menu-editor.vml")
    Vml("RunScript", "SelectionChanged")
end
