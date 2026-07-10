Option Explicit
Dim sUser, sPassword

If Browser("OrangeHRM_BrowserObject").Page("OrangeHRM_PageObject").WebElement("Innertext_WebElement").Exist(10) Then
	Reporter.ReportEvent micPass, Environment("TestName"), "URL wurde im Browser erfolgreich geladen."
Else
	Reporter.ReportEvent micFail, Environment("TestName"), "URL wurde im Browser nicht erfolgreich geladen!"
	ExitTest(-1)
End  If

Browser("OrangeHRM_BrowserObject").Page("OrangeHRM_PageObject").WebEdit("username_WebEdit").Set "Admin" Parameter("Input_User")
Browser("OrangeHRM_BrowserObject").Page("OrangeHRM_PageObject").WebEdit("password_WebEdit").SetSecure Parameter("Input_Password")
Browser("OrangeHRM_BrowserObject").Page("OrangeHRM_PageObject").WebButton("Login_WebButton").Click

