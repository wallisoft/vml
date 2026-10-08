<Global.Microsoft.VisualBasic.CompilerServices.DesignerGenerated()> _
Partial Class SignIn
    Inherits System.Windows.Forms.Form

    Friend WithEvents Logo As System.Windows.Forms.PictureBox
    Friend WithEvents NameLabel As System.Windows.Forms.Label
    Friend WithEvents PassLabel As System.Windows.Forms.Label
    Friend WithEvents txtName As System.Windows.Forms.TextBox
    Friend WithEvents txtPass As System.Windows.Forms.TextBox
    Friend WithEvents OK As System.Windows.Forms.Button
    Friend WithEvents Cancel As System.Windows.Forms.Button

    Private components As System.ComponentModel.IContainer

    'NOTE: The following procedure is required by the Windows Form Designer
    <System.Diagnostics.DebuggerStepThrough()> _
    Private Sub InitializeComponent()
        Dim resources As System.ComponentModel.ComponentResourceManager = New System.ComponentModel.ComponentResourceManager(GetType(SignIn))
        Me.Logo = New System.Windows.Forms.PictureBox
        Me.NameLabel = New System.Windows.Forms.Label
        Me.PassLabel = New System.Windows.Forms.Label
        Me.txtName = New System.Windows.Forms.TextBox
        Me.txtPass = New System.Windows.Forms.TextBox
        Me.OK = New System.Windows.Forms.Button
        Me.Cancel = New System.Windows.Forms.Button
        CType(Me.Logo, System.ComponentModel.ISupportInitialize).BeginInit()
        Me.SuspendLayout()
        '
        'Logo
        '
        Me.Logo.Image = CType(resources.GetObject("Logo.Image"), System.Drawing.Image)
        Me.Logo.Location = New System.Drawing.Point(0, 0)
        Me.Logo.Name = "Logo"
        Me.Logo.Size = New System.Drawing.Size(165, 193)
        Me.Logo.TabIndex = 0
        Me.Logo.TabStop = False
        '
        'NameLabel
        '
        Me.NameLabel.Location = New System.Drawing.Point(172, 24)
        Me.NameLabel.Name = "NameLabel"
        Me.NameLabel.Size = New System.Drawing.Size(220, 23)
        Me.NameLabel.TabIndex = 0
        Me.NameLabel.Text = "&User name"
        Me.NameLabel.TextAlign = System.Drawing.ContentAlignment.MiddleLeft
        '
        'PassLabel
        '
        Me.PassLabel.Location = New System.Drawing.Point(172, 81)
        Me.PassLabel.Name = "PassLabel"
        Me.PassLabel.Size = New System.Drawing.Size(220, 23)
        Me.PassLabel.TabIndex = 2
        Me.PassLabel.Text = "&Password"
        '
        'txtName
        '
        Me.txtName.Location = New System.Drawing.Point(174, 44)
        Me.txtName.Name = "txtName"
        Me.txtName.Size = New System.Drawing.Size(220, 20)
        Me.txtName.TabIndex = 1
        '
        'txtPass
        '
        Me.txtPass.Location = New System.Drawing.Point(174, 101)
        Me.txtPass.Name = "txtPass"
        Me.txtPass.PasswordChar = Global.Microsoft.VisualBasic.ChrW(42)
        Me.txtPass.Size = New System.Drawing.Size(220, 20)
        Me.txtPass.TabIndex = 3
        '
        'OK
        '
        Me.OK.Location = New System.Drawing.Point(197, 161)
        Me.OK.Name = "OK"
        Me.OK.Size = New System.Drawing.Size(94, 23)
        Me.OK.TabIndex = 4
        Me.OK.Text = "&OK"
        '
        'Cancel
        '
        Me.Cancel.DialogResult = System.Windows.Forms.DialogResult.Cancel
        Me.Cancel.Location = New System.Drawing.Point(300, 161)
        Me.Cancel.Name = "Cancel"
        Me.Cancel.Size = New System.Drawing.Size(94, 23)
        Me.Cancel.TabIndex = 5
        Me.Cancel.Text = "&Cancel"
        '
        'SignIn
        '
        Me.AcceptButton = Me.OK
        Me.AutoScaleDimensions = New System.Drawing.SizeF(6.0!, 13.0!)
        Me.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font
        Me.CancelButton = Me.Cancel
        Me.ClientSize = New System.Drawing.Size(401, 193)
        Me.Controls.Add(Me.Cancel)
        Me.Controls.Add(Me.OK)
        Me.Controls.Add(Me.txtPass)
        Me.Controls.Add(Me.txtName)
        Me.Controls.Add(Me.PassLabel)
        Me.Controls.Add(Me.NameLabel)
        Me.Controls.Add(Me.Logo)
        Me.FormBorderStyle = System.Windows.Forms.FormBorderStyle.FixedDialog
        Me.MaximizeBox = False
        Me.Name = "SignIn"
        Me.StartPosition = System.Windows.Forms.FormStartPosition.CenterParent
        Me.Text = "Sign in"
        CType(Me.Logo, System.ComponentModel.ISupportInitialize).EndInit()
        Me.ResumeLayout(False)
        Me.PerformLayout()

    End Sub

End Class
