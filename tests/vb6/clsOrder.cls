VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "clsOrder"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Private mCustomer As String
Private mLines As Collection

Private Sub Class_Initialize()
    Set mLines = New Collection
End Sub

Public Property Get Customer() As String
    Customer = mCustomer
End Property

Public Property Let Customer(ByVal Value As String)
    mCustomer = Trim$(Value)
End Property

Public Sub AddLine(ByVal Product As String, ByVal Quantity As Integer)
    mLines.Add Array(Product, Quantity)
End Sub

Public Function LineCount() As Long
    LineCount = mLines.Count
End Function
