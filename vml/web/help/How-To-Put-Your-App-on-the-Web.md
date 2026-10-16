# How To Put Your App on the Web

## Introduction

Any Visualised form can become a web page: one HTML file, with the Lua engine inside it, that runs in any modern browser on a computer or a phone. No server code is needed; upload the file anywhere that serves web pages.

## Prerequisites

- A form, such as `TipCalc.vml` from [How To Build Your First Visualised App](How-To-Build-Your-First-Visualised-App).

## Step 1: Make the page

```
vml html TipCalc.vml TipCalc.html --open
```

`--open` opens it in your browser when it's made. The page is self-contained: pictures the form uses are put inside it too, and it works offline.

## Step 2: Check it on a phone

In the designer, **View > Preview on Phone** serves the form to phones on the same Wi-Fi and shows a QR code: scan it with the phone's camera. On a phone, the form is scaled to fit the screen's width. Set `PhoneFit=None` on the `@Window` to turn that off.

## Step 3: Put it online

Upload `TipCalc.html` to any web host, as you would any page. Then open its address on your phone and on a computer to check.

## Conclusion

One command turns a form into a page anyone can open. To have people install it as an app on Android, see [How To Turn Your App into an Android App](How-To-Turn-Your-App-into-an-Android-App); to tell them about new versions, see [How To Ship Updates to Your Users](How-To-Ship-Updates-to-Your-Users).
