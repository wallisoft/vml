Attribute VB_Name = "modPricing"
Option Explicit

Public Const VAT_RATE As Double = 0.2

' The price of a number of things, with VAT, to the nearest penny.
Public Function PriceWithVat(ByVal UnitPrice As Currency, ByVal Quantity As Integer) As Currency
    PriceWithVat = Round(UnitPrice * Quantity * (1 + VAT_RATE), 2)
End Function

Public Sub Main()
    frmMain.Show
End Sub
