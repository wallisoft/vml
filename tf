-- Event properties for all controls
INSERT OR REPLACE INTO property_display (control_type, property_name, display_name, display_order, category, editor_type) VALUES
-- Button
('Button', 'OnClick', 'On Click', 900, 'Events', 'script'),
('Button', 'OnPointerPressed', 'On Pointer Pressed', 901, 'Events', 'script'),
('Button', 'OnPointerReleased', 'On Pointer Released', 902, 'Events', 'script'),
-- TextBox
('TextBox', 'OnTextChanged', 'On Text Changed', 900, 'Events', 'script'),
('TextBox', 'OnGotFocus', 'On Got Focus', 901, 'Events', 'script'),
('TextBox', 'OnLostFocus', 'On Lost Focus', 902, 'Events', 'script'),
('TextBox', 'OnKeyDown', 'On Key Down', 903, 'Events', 'script'),
('TextBox', 'OnKeyUp', 'On Key Up', 904, 'Events', 'script'),
-- CheckBox
('CheckBox', 'OnChecked', 'On Checked', 900, 'Events', 'script'),
('CheckBox', 'OnUnchecked', 'On Unchecked', 901, 'Events', 'script'),
-- RadioButton
('RadioButton', 'OnChecked', 'On Checked', 900, 'Events', 'script'),
('RadioButton', 'OnUnchecked', 'On Unchecked', 901, 'Events', 'script'),
-- ComboBox
('ComboBox', 'OnSelectionChanged', 'On Selection Changed', 900, 'Events', 'script'),
('ComboBox', 'OnDropDownOpened', 'On DropDown Opened', 901, 'Events', 'script'),
('ComboBox', 'OnDropDownClosed', 'On DropDown Closed', 902, 'Events', 'script'),
-- ListBox
('ListBox', 'OnSelectionChanged', 'On Selection Changed', 900, 'Events', 'script'),
('ListBox', 'OnDoubleTapped', 'On Double Tapped', 901, 'Events', 'script'),
-- Slider
('Slider', 'OnValueChanged', 'On Value Changed', 900, 'Events', 'script'),
-- NumericUpDown
('NumericUpDown', 'OnValueChanged', 'On Value Changed', 900, 'Events', 'script'),
-- DatePicker
('DatePicker', 'OnDateChanged', 'On Date Changed', 900, 'Events', 'script'),
-- TimePicker
('TimePicker', 'OnTimeChanged', 'On Time Changed', 900, 'Events', 'script'),
-- ToggleSwitch
('ToggleSwitch', 'OnChecked', 'On Checked', 900, 'Events', 'script'),
('ToggleSwitch', 'OnUnchecked', 'On Unchecked', 901, 'Events', 'script'),
-- Window
('Window', 'OnOpened', 'On Opened', 900, 'Events', 'script'),
('Window', 'OnClosing', 'On Closing', 901, 'Events', 'script'),
('Window', 'OnClosed', 'On Closed', 902, 'Events', 'script'),
('Window', 'OnActivated', 'On Activated', 903, 'Events', 'script'),
-- MenuItem
('MenuItem', 'OnClick', 'On Click', 900, 'Events', 'script'),
-- TabControl
('TabControl', 'OnSelectionChanged', 'On Selection Changed', 900, 'Events', 'script'),
-- TreeView
('TreeView', 'OnSelectionChanged', 'On Selection Changed', 900, 'Events', 'script'),
-- TreeViewItem
('TreeViewItem', 'OnExpanded', 'On Expanded', 900, 'Events', 'script'),
('TreeViewItem', 'OnCollapsed', 'On Collapsed', 901, 'Events', 'script'),
-- Expander
('Expander', 'OnExpanded', 'On Expanded', 900, 'Events', 'script'),
('Expander', 'OnCollapsed', 'On Collapsed', 901, 'Events', 'script');
