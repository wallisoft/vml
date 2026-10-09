VERSION 5.00
Object = "{5E9E78A0-531B-11CF-91F6-C2863C385E30}#1.0#0"; "MSFLXGRD.OCX"
Object = "{F9043C88-F6F2-101A-A3C9-08002B2F49FB}#1.2#0"; "COMDLG32.OCX"
Object = "{831FDD16-0C5C-11D2-A9FC-0000F8754DA1}#2.0#0"; "MSCOMCTL.OCX"
Begin VB.Form frmMain 
   BackColor       =   &H00C0E0FF&
   Caption         =   "Corner Shop - Orders"
   ClientHeight    =   6300
   ClientLeft      =   165
   ClientTop       =   735
   ClientWidth     =   9000
   LinkTopic       =   "Form1"
   ScaleHeight     =   6300
   ScaleWidth      =   9000
   StartUpPosition =   3  'Windows Default
   Begin MSComctlLib.Slider sldDiscount 
      Height          =   390
      Left            =   6000
      TabIndex        =   18
      Top             =   5640
      Width           =   2760
      _ExtentX        =   4868
      _ExtentY        =   688
      _Version        =   393216
      Max             =   50
      TickFrequency   =   5
   End
   Begin MSComDlg.CommonDialog dlgFile 
      Left            =   7800
      Top             =   5640
      _ExtentX        =   847
      _ExtentY        =   847
      _Version        =   393216
      Filter          =   "Orders (*.ord)|*.ord"
   End
   Begin MSFlexGridLib.MSFlexGrid grdOrders 
      Height          =   1620
      Left            =   240
      TabIndex        =   17
      Top             =   3840
      Width           =   8520
      _ExtentX        =   15028
      _ExtentY        =   2858
      _Version        =   393216
      Cols            =   3
      FixedCols       =   0
      FormatString    =   "<Product|>Qty|>Price"
   End
   Begin VB.PictureBox picToolbar 
      Align           =   1  'Align Top
      BorderStyle     =   0  'None
      Height          =   480
      Left            =   0
      ScaleHeight     =   32
      ScaleMode       =   3  'Pixel
      ScaleWidth      =   600
      TabIndex        =   15
      Top             =   0
      Width           =   9000
      Begin VB.CommandButton cmdRefresh 
         Caption         =   "&Refresh"
         Height          =   24
         Left            =   8
         TabIndex        =   16
         Top             =   4
         Width           =   80
      End
   End
   Begin VB.Timer tmrClock 
      Interval        =   1000
      Left            =   8400
      Top             =   5640
   End
   Begin VB.CommandButton cmdQty 
      Caption         =   "+10"
      Height          =   375
      Index           =   2
      Left            =   2400
      TabIndex        =   14
      Top             =   3240
      Width           =   975
   End
   Begin VB.CommandButton cmdQty 
      Caption         =   "+5"
      Height          =   375
      Index           =   1
      Left            =   1320
      TabIndex        =   13
      Top             =   3240
      Width           =   975
   End
   Begin VB.CommandButton cmdQty 
      Caption         =   "+1"
      Height          =   375
      Index           =   0
      Left            =   240
      TabIndex        =   12
      Top             =   3240
      Width           =   975
   End
   Begin VB.CommandButton cmdDelete 
      BackColor       =   &H008080FF&
      Caption         =   "&Delete"
      Enabled         =   0   'False
      Height          =   375
      Left            =   7560
      Style           =   1  'Graphical
      TabIndex        =   11
      Top             =   3240
      Width           =   1200
   End
   Begin VB.ListBox lstProducts 
      Height          =   2010
      ItemData        =   "frmMain.frx":0079
      Left            =   6000
      List            =   "frmMain.frx":0052
      TabIndex        =   10
      Top             =   960
      Width           =   2760
   End
   Begin VB.ComboBox cboCategory 
      Height          =   315
      Left            =   6000
      List            =   "frmMain.frx":00AE
      Style           =   2  'Dropdown List
      TabIndex        =   9
      Top             =   600
      Width           =   2760
   End
   Begin VB.TextBox txtPin 
      Height          =   315
      IMEMode         =   3  'DISABLE
      Left            =   1560
      PasswordChar    =   "*"
      TabIndex        =   8
      Top             =   2760
      Width           =   1200
   End
   Begin VB.TextBox txtTotal 
      Height          =   315
      Left            =   4320
      Locked          =   -1  'True
      TabIndex        =   7
      Text            =   "0.00"
      Top             =   2760
      Width           =   1335
   End
   Begin VB.TextBox txtNotes 
      Height          =   975
      Left            =   1560
      MultiLine       =   -1  'True
      ScrollBars      =   2  'Vertical
      TabIndex        =   6
      Text            =   "frmMain.frx":0089
      Top             =   1680
      Width           =   4095
   End
   Begin VB.TextBox txtCustomer 
      Height          =   315
      Left            =   1560
      TabIndex        =   1
      ToolTipText     =   "Who the order is for ('Mr' or ""Mrs"" too)"
      Top             =   600
      Width           =   4095
   End
   Begin VB.Frame fraDelivery 
      Caption         =   "Deli&very"
      Height          =   615
      Left            =   1560
      TabIndex        =   2
      Top             =   1020
      Width           =   4095
      Begin VB.CheckBox chkGift 
         Caption         =   "&Gift wrap"
         Height          =   255
         Left            =   2760
         TabIndex        =   5
         Top             =   240
         Value           =   1  'Checked
         Width           =   1215
      End
      Begin VB.OptionButton optExpress 
         Caption         =   "E&xpress"
         Height          =   255
         Left            =   1440
         TabIndex        =   4
         Top             =   240
         Width           =   1215
      End
      Begin VB.OptionButton optStandard 
         Caption         =   "&Standard"
         Height          =   255
         Left            =   120
         TabIndex        =   3
         Top             =   240
         Value           =   -1  'True
         Width           =   1215
      End
   End
   Begin VB.Line linRule 
      BorderColor     =   &H00808080&
      X1              =   240
      X2              =   8760
      Y1              =   3720
      Y2              =   3720
   End
   Begin VB.Image imgLogo 
      Height          =   480
      Left            =   240
      Picture         =   "frmMain.frx":0000
      Stretch         =   -1  'True
      Top             =   600
      Width           =   480
   End
   Begin VB.Label lblStatus 
      Alignment       =   2  'Center
      Caption         =   "Saved"
      Height          =   255
      Left            =   240
      TabIndex        =   21
      Top             =   5700
      Visible         =   0   'False
      Width           =   3000
   End
   Begin VB.Label lblTotal 
      Alignment       =   1  'Right Justify
      BackColor       =   &H80000018&
      Caption         =   "Total (£):"
      BeginProperty Font 
         Name            =   "Arial"
         Size            =   12
         Charset         =   0
         Weight          =   700
         Underline       =   0   'False
         Italic          =   0   'False
         Strikethrough   =   0   'False
      EndProperty
      ForeColor       =   &H00800000&
      Height          =   255
      Left            =   3000
      TabIndex        =   20
      Top             =   2790
      Width           =   1215
   End
   Begin VB.Label lblCustomer 
      Caption         =   "&Customer:"
      Height          =   255
      Left            =   840
      TabIndex        =   0
      Top             =   630
      Width           =   675
   End
   Begin VB.Menu mnuFile 
      Caption         =   "&File"
      Begin VB.Menu mnuFileNew 
         Caption         =   "&New Order"
         Shortcut        =   ^N
      End
      Begin VB.Menu mnuFileRecent 
         Caption         =   "&Recent"
         Begin VB.Menu mnuRecent 
            Caption         =   "Smith && Sons"
            Index           =   0
         End
         Begin VB.Menu mnuRecent 
            Caption         =   "Patel's"
            Index           =   1
         End
      End
      Begin VB.Menu mnuFileSep 
         Caption         =   "-"
      End
      Begin VB.Menu mnuFileExit 
         Caption         =   "E&xit"
         Shortcut        =   ^{F4}
      End
   End
   Begin VB.Menu mnuEdit 
      Caption         =   "&Edit"
      Begin VB.Menu mnuEditDelete 
         Caption         =   "&Delete Line"
         Enabled         =   0   'False
         Shortcut        =   {DEL}
      End
   End
   Begin VB.Menu mnuHelp 
      Caption         =   "&Help"
      Begin VB.Menu mnuHelpContents 
         Caption         =   "&Contents"
         Shortcut        =   {F1}
      End
      Begin VB.Menu mnuHelpTips 
         Caption         =   "Show &Tips"
         Checked         =   -1  'True
         Shortcut        =   +{F1}
      End
      Begin VB.Menu mnuHelpAbout 
         Caption         =   "&About ""Corner Shop""..."
      End
   End
End
Attribute VB_Name = "frmMain"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Option Explicit

Private Declare Function GetTickCount Lib "kernel32" () As Long

Dim mOrder As clsOrder
Private mDirty As Boolean

Private Sub Form_Load()
    Set mOrder = New clsOrder
    grdOrders.Rows = 1
    RefreshTotals
End Sub

Private Sub Form_Activate()
    txtCustomer.SetFocus
End Sub

Private Sub Form_Resize()
    If WindowState <> vbMinimized Then
        grdOrders.Width = ScaleWidth - 480
    End If
End Sub

Private Sub Form_Unload(Cancel As Integer)
    If mDirty Then
        Cancel = (MsgBox("Leave without saving?", vbYesNo) = vbNo)
    End If
End Sub

' One handler for all three quantity buttons.
Private Sub cmdQty_Click(Index As Integer)
    Dim n As Integer
    n = Choose(Index + 1, 1, 5, 10)
    If lstProducts.ListIndex < 0 Then Exit Sub
    mOrder.AddLine lstProducts.Text, n
    mDirty = True
    RefreshTotals
End Sub

Private Sub cmdRefresh_Click()
    RefreshTotals
End Sub

Private Sub mnuFileNew_Click()
    Set mOrder = New clsOrder
    txtCustomer.Text = ""
    RefreshTotals
End Sub

Private Sub mnuRecent_Click(Index As Integer)
    txtCustomer.Text = mnuRecent(Index).Caption
End Sub

Private Sub mnuFileExit_Click()
    Unload Me
End Sub

Private Sub mnuHelpAbout_Click()
    frmAbout.Show vbModal, Me
End Sub

Private Sub txtCustomer_Change()
    mOrder.Customer = txtCustomer.Text
    mDirty = True
End Sub

Private Sub txtCustomer_KeyPress(KeyAscii As Integer)
    If KeyAscii = vbKeyReturn Then KeyAscii = 0
End Sub

Private Sub txtPin_KeyPress(KeyAscii As Integer)
    If KeyAscii < vbKey0 Or KeyAscii > vbKey9 Then KeyAscii = 0
End Sub

Private Sub txtPin_KeyDown(KeyCode As Integer, Shift As Integer)
    If KeyCode = vbKeyEscape Then txtPin.Text = ""
End Sub

Private Sub lstProducts_Click()
    lblStatus.Visible = False
End Sub

Private Sub lstProducts_DblClick()
    cmdQty_Click 0
End Sub

Private Sub cboCategory_Click()
    lstProducts.ListIndex = -1
End Sub

Private Sub chkGift_Click()
    mDirty = True
End Sub

Private Sub imgLogo_Click()
    frmAbout.Show vbModal, Me
End Sub

Private Sub grdOrders_DblClick()
    If grdOrders.Row > 0 Then cmdDelete.Enabled = True
End Sub

Private Sub sldDiscount_Change()
    RefreshTotals
End Sub

Private Sub tmrClock_Timer()
    Caption = "Corner Shop - Orders  " & Format$(Now, "hh:nn")
End Sub

Private Function LineTotal(ByVal UnitPrice As Currency, ByVal Quantity As Integer) As Currency
    LineTotal = PriceWithVat(UnitPrice, Quantity) * (100 - sldDiscount.Value) / 100
End Function

Private Sub RefreshTotals()
    Dim i As Long, total As Currency
    For i = 1 To grdOrders.Rows - 1
        total = total + LineTotal(Val(grdOrders.TextMatrix(i, 2)), Val(grdOrders.TextMatrix(i, 1)))
    Next i
    txtTotal.Text = Format$(total, "0.00")
End Sub
