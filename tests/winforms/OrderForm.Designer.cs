namespace Shop
{
    partial class OrderForm
    {
        private System.ComponentModel.IContainer components = null;

        private void InitializeComponent()
        {
            this.components = new System.ComponentModel.Container();
            this.menuStrip1 = new System.Windows.Forms.MenuStrip();
            this.fileMenu = new System.Windows.Forms.ToolStripMenuItem();
            this.newItem = new System.Windows.Forms.ToolStripMenuItem();
            this.sep1 = new System.Windows.Forms.ToolStripSeparator();
            this.exitItem = new System.Windows.Forms.ToolStripMenuItem();
            this.helpMenu = new System.Windows.Forms.ToolStripMenuItem();
            this.aboutItem = new System.Windows.Forms.ToolStripMenuItem();
            this.tabs = new System.Windows.Forms.TabControl();
            this.pageOrder = new System.Windows.Forms.TabPage();
            this.pageNotes = new System.Windows.Forms.TabPage();
            this.lblCustomer = new System.Windows.Forms.Label();
            this.txtCustomer = new System.Windows.Forms.TextBox();
            this.cmbSize = new System.Windows.Forms.ComboBox();
            this.chkGift = new System.Windows.Forms.CheckBox();
            this.optExpress = new System.Windows.Forms.RadioButton();
            this.grpTotals = new System.Windows.Forms.GroupBox();
            this.lblTotal = new System.Windows.Forms.Label();
            this.txtNotes = new System.Windows.Forms.TextBox();
            this.table = new System.Windows.Forms.TableLayoutPanel();
            this.btnSave = new System.Windows.Forms.Button();
            this.btnCancel = new System.Windows.Forms.Button();
            this.grid = new System.Windows.Forms.DataGridView();
            this.timer1 = new System.Windows.Forms.Timer(this.components);
            this.menuStrip1.SuspendLayout();
            this.SuspendLayout();
            // 
            // menuStrip1
            // 
            this.menuStrip1.Items.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.fileMenu,
            this.helpMenu});
            this.menuStrip1.Location = new System.Drawing.Point(0, 0);
            this.menuStrip1.Name = "menuStrip1";
            this.menuStrip1.Size = new System.Drawing.Size(520, 24);
            // 
            // fileMenu
            // 
            this.fileMenu.DropDownItems.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.newItem,
            this.sep1,
            this.exitItem});
            this.fileMenu.Name = "fileMenu";
            this.fileMenu.Text = "&File";
            // 
            // newItem
            // 
            this.newItem.Name = "newItem";
            this.newItem.ShortcutKeys = ((System.Windows.Forms.Keys)((System.Windows.Forms.Keys.Control | System.Windows.Forms.Keys.N)));
            this.newItem.Text = "&New order";
            this.newItem.Click += new System.EventHandler(this.newItem_Click);
            // 
            // exitItem
            // 
            this.exitItem.Name = "exitItem";
            this.exitItem.Text = "E&xit";
            // 
            // helpMenu
            // 
            this.helpMenu.DropDownItems.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.aboutItem});
            this.helpMenu.Name = "helpMenu";
            this.helpMenu.Text = "&Help";
            // 
            // aboutItem
            // 
            this.aboutItem.Name = "aboutItem";
            this.aboutItem.ShortcutKeys = System.Windows.Forms.Keys.F1;
            this.aboutItem.Text = "&About \"Orders\"";
            // 
            // tabs
            // 
            this.tabs.Anchor = ((System.Windows.Forms.AnchorStyles)((((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Bottom) 
            | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.tabs.Controls.Add(this.pageOrder);
            this.tabs.Controls.Add(this.pageNotes);
            this.tabs.Location = new System.Drawing.Point(12, 36);
            this.tabs.Name = "tabs";
            this.tabs.Size = new System.Drawing.Size(496, 220);
            // 
            // pageOrder
            // 
            this.pageOrder.Controls.Add(this.grpTotals);
            this.pageOrder.Controls.Add(this.optExpress);
            this.pageOrder.Controls.Add(this.chkGift);
            this.pageOrder.Controls.Add(this.cmbSize);
            this.pageOrder.Controls.Add(this.txtCustomer);
            this.pageOrder.Controls.Add(this.lblCustomer);
            this.pageOrder.Location = new System.Drawing.Point(4, 22);
            this.pageOrder.Name = "pageOrder";
            this.pageOrder.Size = new System.Drawing.Size(488, 194);
            this.pageOrder.Text = "Order";
            // 
            // pageNotes
            // 
            this.pageNotes.Controls.Add(this.txtNotes);
            this.pageNotes.Location = new System.Drawing.Point(4, 22);
            this.pageNotes.Name = "pageNotes";
            this.pageNotes.Size = new System.Drawing.Size(488, 194);
            this.pageNotes.Text = "Notes";
            // 
            // lblCustomer
            // 
            this.lblCustomer.AutoSize = true;
            this.lblCustomer.Location = new System.Drawing.Point(16, 18);
            this.lblCustomer.Name = "lblCustomer";
            this.lblCustomer.Size = new System.Drawing.Size(54, 13);
            this.lblCustomer.Text = "&Customer:";
            // 
            // txtCustomer
            // 
            this.txtCustomer.Anchor = ((System.Windows.Forms.AnchorStyles)(((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Left) 
            | System.Windows.Forms.AnchorStyles.Right)));
            this.txtCustomer.Location = new System.Drawing.Point(90, 15);
            this.txtCustomer.Name = "txtCustomer";
            this.txtCustomer.Size = new System.Drawing.Size(200, 20);
            this.txtCustomer.TextChanged += new System.EventHandler(this.txtCustomer_TextChanged);
            // 
            // cmbSize
            // 
            this.cmbSize.Items.AddRange(new object[] {
            "Small",
            "Medium",
            "Large"});
            this.cmbSize.Location = new System.Drawing.Point(90, 45);
            this.cmbSize.Name = "cmbSize";
            this.cmbSize.Size = new System.Drawing.Size(121, 21);
            // 
            // chkGift
            // 
            this.chkGift.AutoSize = true;
            this.chkGift.Checked = true;
            this.chkGift.Location = new System.Drawing.Point(90, 78);
            this.chkGift.Name = "chkGift";
            this.chkGift.Size = new System.Drawing.Size(73, 17);
            this.chkGift.Text = "Gift &wrap";
            // 
            // optExpress
            // 
            this.optExpress.AutoSize = true;
            this.optExpress.Location = new System.Drawing.Point(90, 104);
            this.optExpress.Name = "optExpress";
            this.optExpress.Size = new System.Drawing.Size(62, 17);
            this.optExpress.Text = "Express";
            // 
            // grpTotals
            // 
            this.grpTotals.Controls.Add(this.lblTotal);
            this.grpTotals.Location = new System.Drawing.Point(310, 10);
            this.grpTotals.Name = "grpTotals";
            this.grpTotals.Size = new System.Drawing.Size(160, 70);
            this.grpTotals.Text = "Totals";
            // 
            // lblTotal
            // 
            this.lblTotal.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(255)))), ((int)(((byte)(255)))), ((int)(((byte)(192)))));
            this.lblTotal.Font = new System.Drawing.Font("Arial", 12F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.lblTotal.ForeColor = System.Drawing.Color.Navy;
            this.lblTotal.Location = new System.Drawing.Point(12, 24);
            this.lblTotal.Name = "lblTotal";
            this.lblTotal.Size = new System.Drawing.Size(136, 30);
            this.lblTotal.Text = "£0.00";
            this.lblTotal.TextAlign = System.Drawing.ContentAlignment.MiddleRight;
            // 
            // txtNotes
            // 
            this.txtNotes.Dock = System.Windows.Forms.DockStyle.Fill;
            this.txtNotes.Location = new System.Drawing.Point(0, 0);
            this.txtNotes.Multiline = true;
            this.txtNotes.Name = "txtNotes";
            this.txtNotes.Size = new System.Drawing.Size(488, 194);
            // 
            // table
            // 
            this.table.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Bottom | System.Windows.Forms.AnchorStyles.Right)));
            this.table.ColumnCount = 2;
            this.table.Controls.Add(this.btnSave, 0, 0);
            this.table.Controls.Add(this.btnCancel, 1, 0);
            this.table.Location = new System.Drawing.Point(348, 380);
            this.table.Name = "table";
            this.table.RowCount = 1;
            this.table.Size = new System.Drawing.Size(160, 30);
            // 
            // btnSave
            // 
            this.btnSave.Location = new System.Drawing.Point(3, 3);
            this.btnSave.Name = "btnSave";
            this.btnSave.Size = new System.Drawing.Size(74, 23);
            this.btnSave.Text = "&Save";
            this.btnSave.Click += new System.EventHandler(this.btnSave_Click);
            // 
            // btnCancel
            // 
            this.btnCancel.Enabled = false;
            this.btnCancel.Location = new System.Drawing.Point(83, 3);
            this.btnCancel.Name = "btnCancel";
            this.btnCancel.Size = new System.Drawing.Size(74, 23);
            this.btnCancel.Text = "Cancel";
            // 
            // grid
            // 
            this.grid.Location = new System.Drawing.Point(12, 266);
            this.grid.Name = "grid";
            this.grid.Size = new System.Drawing.Size(496, 104);
            // 
            // OrderForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 13F);
            this.ClientSize = new System.Drawing.Size(520, 422);
            this.Controls.Add(this.grid);
            this.Controls.Add(this.table);
            this.Controls.Add(this.tabs);
            this.Controls.Add(this.menuStrip1);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedDialog;
            this.MainMenuStrip = this.menuStrip1;
            this.Name = "OrderForm";
            this.Text = "New order";
            this.Load += new System.EventHandler(this.OrderForm_Load);
            this.menuStrip1.ResumeLayout(false);
            this.ResumeLayout(false);
        }

        private System.Windows.Forms.MenuStrip menuStrip1;
        private System.Windows.Forms.ToolStripMenuItem fileMenu;
        private System.Windows.Forms.Button btnSave;
    }
}
