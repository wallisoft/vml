VERSION 5.00
Object = "{BDC217C8-ED16-11CD-956C-0000C04E4C0A}#1.1#0"; "TABCTL32.OCX"
Object = "{831FDD16-0C5C-11D2-A9FC-0000F8754DA1}#2.0#0"; "MSCOMCTL.OCX"
Begin VB.Form frmExtras 
   BorderStyle     =   1  'Fixed Single
   Caption         =   "Stock && Suppliers"
   ClientHeight    =   4500
   ClientLeft      =   45
   ClientTop       =   330
   ClientWidth     =   6000
   LinkTopic       =   "Form1"
   ScaleHeight     =   300
   ScaleMode       =   3  'Pixel
   ScaleWidth      =   400
   Begin VB.Data datStock 
      Caption         =   "Stock"
      Connect         =   "Access"
      DatabaseName    =   "stock.mdb"
      Height          =   23
      Left            =   8
      Top             =   270
      Visible         =   0   'False
      Width           =   120
   End
   Begin VB.HScrollBar hsbZoom 
      Height          =   17
      Left            =   200
      Max             =   10
      TabIndex        =   9
      Top             =   240
      Width           =   190
   End
   Begin VB.HScrollBar hsbPan 
      Height          =   17
      Left            =   200
      TabIndex        =   8
      Top             =   270
      Width           =   190
   End
   Begin MSComctlLib.TreeView tvwGroups 
      Height          =   100
      Left            =   8
      TabIndex        =   7
      Top             =   130
      Width           =   120
      _ExtentX        =   3175
      _ExtentY        =   2646
      _Version        =   393217
      Style           =   7
      Appearance      =   1
   End
   Begin MSComctlLib.ListView lvwStock 
      Height          =   100
      Left            =   136
      TabIndex        =   6
      Top             =   130
      Width           =   256
      _ExtentX        =   6773
      _ExtentY        =   2646
      View            =   3
      _Version        =   393217
      NumItems        =   2
      BeginProperty ColumnHeader(1) {BDD1F052-858B-11D1-B16A-00C0F0283628} 
         Text            =   "Item"
         Object.Width           =   2540
      EndProperty
      BeginProperty ColumnHeader(2) {BDD1F052-858B-11D1-B16A-00C0F0283628} 
         SubItemIndex    =   1
         Text            =   "In stock"
         Object.Width           =   1764
      EndProperty
   End
   Begin TabDlg.SSTab tabDetails 
      Height          =   110
      Left            =   136
      TabIndex        =   3
      Top             =   8
      Width           =   256
      _ExtentX        =   6773
      _ExtentY        =   2910
      _Version        =   393216
      Tabs            =   2
      TabsPerRow      =   2
      TabHeight       =   520
      TabCaption(0)   =   "&Address"
      TabPicture(0)   =   "frmExtras.frx":0000
      Tab(0).ControlEnabled=   -1  'True
      Tab(0).Control(0)=   "txtStreet"
      Tab(0).Control(0).Enabled=   0   'False
      Tab(0).ControlCount=   1
      TabCaption(1)   =   "Notes"
      TabPicture(1)   =   "frmExtras.frx":001C
      Tab(1).ControlEnabled=   0   'False
      Tab(1).Control(0)=   "txtMemo"
      Tab(1).ControlCount=   1
      Begin VB.TextBox txtMemo 
         Height          =   855
         Left            =   -74760
         MultiLine       =   -1  'True
         TabIndex        =   5
         Top             =   540
         Width           =   3300
      End
      Begin VB.TextBox txtStreet 
         Height          =   315
         Left            =   240
         TabIndex        =   4
         Text            =   "1 High Street"
         Top             =   540
         Width           =   3300
      End
   End
   Begin VB.PictureBox picGauge 
      Height          =   50
      Left            =   8
      ScaleHeight     =   12.171
      ScaleMode       =   6  'Millimeter
      ScaleWidth      =   30.692
      TabIndex        =   1
      Top             =   68
      Width           =   120
      Begin VB.Label lblGauge 
         Caption         =   "Level"
         Height          =   4
         Left            =   2
         TabIndex        =   2
         Top             =   2
         Width           =   20
      End
   End
   Begin VB.Image imgSupplier 
      Height          =   48
      Left            =   80
      Picture         =   "frmExtras.frx":0038
      Top             =   8
      Width           =   48
   End
   Begin VB.Line linSlope 
      BorderWidth     =   2
      X1              =   8
      X2              =   60
      Y1              =   236
      Y2              =   262
   End
   Begin VB.Shape shpLamp 
      BorderColor     =   &H00000080&
      FillColor       =   &H0000FF00&
      FillStyle       =   0  'Solid
      Height          =   24
      Left            =   8
      Shape           =   3  'Circle
      Top             =   8
      Width           =   24
   End
   Begin VB.Label lblHint 
      AutoSize        =   -1  'True
      BackStyle       =   0  'Transparent
      Caption         =   "Fish && Chips"
      ForeColor       =   &H80000011&
      Height          =   13
      Left            =   8
      TabIndex        =   0
      Top             =   40
      UseMnemonic     =   0   'False
      Width           =   58
   End
End
Attribute VB_Name = "frmExtras"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
