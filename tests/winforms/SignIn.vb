Imports System.Windows.Forms

Public Class SignIn

    Private attempts As Integer = 0

    Private Sub SignIn_Load(sender As System.Object, e As System.EventArgs) Handles MyBase.Load
        txtName.Focus()
    End Sub

    Private Sub OK_Click(ByVal sender As System.Object, _
                         ByVal e As System.EventArgs) Handles OK.Click

        attempts += 1
        If txtName.Text.Trim = "" Then
            MessageBox.Show("Please enter your name")
            Return
        End If
        Me.Close()

    End Sub

    Private Sub Cancel_Click(ByVal sender As System.Object, ByVal e As System.EventArgs) Handles Cancel.Click
        Me.Close()
    End Sub

    Private Function TooManyAttempts() As Boolean
        Return attempts > 3
    End Function

End Class
