VERSION 5.00
Object = "{00028C01-0000-0000-0000-000000000046}#1.0#0"; "DBGRID32.OCX"
Object = "{FAEEE763-117E-101B-8933-08002B2F4F5A}#1.1#0"; "DBLIST32.OCX"
Begin VB.Form frmStock 
   Caption         =   "Stock"
   ClientHeight    =   4200
   ClientLeft      =   60
   ClientTop       =   345
   ClientWidth     =   7200
   LinkTopic       =   "Form1"
   ScaleHeight     =   4200
   ScaleWidth      =   7200
   StartUpPosition =   3  'Windows Default
   Begin VB.CommandButton cmdClose 
      Caption         =   "&Close"
      Height          =   375
      Left            =   5760
      TabIndex        =   5
      Top             =   3720
      Width           =   1215
   End
   Begin VB.CommandButton cmdAbout 
      Caption         =   "&About..."
      Height          =   375
      Left            =   4440
      TabIndex        =   4
      Top             =   3720
      Width           =   1215
   End
   Begin VB.CommandButton cmdCount 
      Caption         =   "Cou&nt"
      Height          =   375
      Left            =   3120
      TabIndex        =   6
      Top             =   3720
      Width           =   1215
   End
   Begin VB.TextBox txtPrice 
      DataField       =   "price"
      DataSource      =   "datStock"
      Height          =   315
      Left            =   240
      TabIndex        =   3
      Top             =   3720
      Width           =   1335
   End
   Begin VB.Data datStock 
      Caption         =   "Stock"
      Connect         =   "Access"
      DatabaseName    =   "C:\Shop\stock.mdb"
      DefaultCursorType=   0  'DefaultCursor
      DefaultType     =   2  'UseODBC
      Exclusive       =   0   'False
      Height          =   345
      Left            =   1680
      Options         =   0
      ReadOnly        =   0   'False
      RecordsetType   =   1  'Dynaset
      RecordSource    =   "items"
      Top             =   3720
      Width           =   1335
   End
   Begin VB.Data datDear 
      Connect         =   "Access"
      DatabaseName    =   "C:\Shop\stock.mdb"
      Height          =   345
      Left            =   1680
      RecordSource    =   "SELECT name, price FROM items WHERE price > 2;"
      Top             =   3300
      Visible         =   0   'False
      Width           =   1335
   End
   Begin MSDBGrid.DBGrid grdStock 
      Bindings        =   "frmStock.frx":0000
      DataSource      =   "datStock"
      Height          =   3015
      Left            =   240
      OleObjectBlob   =   "frmStock.frx":0014
      TabIndex        =   0
      Top             =   240
      Width           =   4335
   End
   Begin MSDBCtls.DBList lstNames 
      Bindings        =   "frmStock.frx":09E2
      Height          =   1425
      Left            =   4800
      TabIndex        =   1
      Top             =   240
      Width           =   2175
      _ExtentX        =   3836
      _ExtentY        =   2514
      _Version        =   393216
      ListField       =   "name"
      RowSource       =   "datStock"
   End
   Begin MSDBCtls.DBCombo cboDear 
      Height          =   315
      Left            =   4800
      TabIndex        =   2
      Top             =   1920
      Width           =   2175
      _ExtentX        =   3836
      _ExtentY        =   556
      _Version        =   393216
      ListField       =   "name"
      RowSource       =   "datDear"
      Text            =   ""
   End
End
Attribute VB_Name = "frmStock"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Option Explicit

Private Sub Form_Load()
    On Error GoTo NoData
    Caption = "Stock"
    cmdCount.Enabled = True
    Exit Sub
NoData:
    MsgBox "The stock database could not be opened.", vbExclamation, "Stock"
End Sub

Private Sub cmdAbout_Click()
    frmAbout.Show vbModal, Me
End Sub

Private Sub cmdCount_Click()
    If grdStock.Row < 0 Then
        MsgBox "Nothing is selected."
        Exit Sub
    End If
    MsgBox "There are " & datStock.Recordset.RecordCount & " items."
    MsgBox "Counted: ""done""." & vbCrLf & "Thank you.", vbInformation, "Stock"
    cmdCount.Caption = "Counted"
End Sub

Private Sub cmdClose_Click()
    If Not Saved() Then Exit Sub
    Unload Me
End Sub

Private Sub Form_Unload(Cancel As Integer)
    MsgBox "Goodbye"
End Sub

Private Function Saved() As Boolean
    Saved = True
End Function
