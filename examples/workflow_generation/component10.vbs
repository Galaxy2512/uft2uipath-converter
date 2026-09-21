If Browser("Application").Page("Login").WebElement("Ready").Exist(10) Then
    Browser("Application").Page("Login").WebEdit("Username").Set Parameter("Input_User")
    Browser("Application").Page("Login").WebButton("Submit").Click
Else
    Browser("Application").Page("Login").WebButton("Retry").Click
End If
