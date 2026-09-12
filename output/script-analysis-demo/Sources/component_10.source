Option Explicit
Dim userName

If Browser("Application").Page("Login").WebElement("Ready").Exist(10) Then
    Reporter.ReportEvent micPass, Environment("TestName"), "Page ready"
Else
    Reporter.ReportEvent micFail, Environment("TestName"), "Page missing"
    ExitTest(-1)
End  If

Browser("Application").Page("Login").WebEdit("Username").Set Parameter("Input_User")
Browser("Application").Page("Login").WebEdit("Password").SetSecure Parameter("Input_Password")
Browser("Application").Page("Login").WebButton("Submit").Click
