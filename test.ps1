# Test POST feedback
\ = @{
    customer_id = 'CUST001'
    feedback_text = 'This product is absolutely amazing! I love it.'
    timestamp = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:5000/feedback' -Method Post -Body \ -ContentType 'application/json'
# Test GET by sentiment after worker processes
Start-Sleep -Seconds 10
Invoke-RestMethod -Uri 'http://localhost:5000/feedback?sentiment=positive&limit=5'
