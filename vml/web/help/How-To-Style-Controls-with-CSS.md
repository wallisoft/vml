# How To Style Controls with CSS

## Introduction

Any control in Visualised can be styled with CSS: colours, borders, rounded corners, gradients, shadows and what happens under the pointer. Write it once and it looks the same on the desktop and on the web. On the web you get everything CSS can do. On the desktop you get colours, gradients, borders, corners, padding, fonts, the hover and pressed states, and shadows; anything else (animations, transforms) is left out there, and the log says so once.

There are three ways in, and they stack:

1. **Properties** such as `Background`, `CornerRadius`, `Shadow`, `GradientTo` and `HoverBackground`.
2. **Shared styles**: `@Style` blocks that any control can use, by name, with `Class=`.
3. **A control's own CSS**, with `Style=`.

When they disagree, the later one wins: properties, then shared styles, then the control's own CSS.

## Prerequisites

- Visualised installed, and a form to work on. [How To Build Your First Visualised App](How-To-Build-Your-First-Visualised-App) makes one.

## Step 1: Make a shared style

A `@Style` block can go anywhere in the form. Its CSS sits between `<<CSS` and `CSS`, and states go in `:hover { }`, `:pressed { }`, `:focus { }`, `:disabled { }` and `:checked { }` blocks:

```
@Style pill
<<CSS
background: #FFFFFF; color: #4F46E5; border: 2px solid #C7D2FE; border-radius: 20px; font-weight: 600
:hover { background: #EEF2FF }
:pressed { background: #E0E7FF }
CSS

@Style big
<<CSS
font-size: 16px
CSS
```

Use them with `Class=`. A control can have several, applied in order:

```
@Button btnShared
Parent=c
Canvas.Left=20
Canvas.Top=20
Width=150
Height=40
Content=Shared style
Class=pill big
```

## Step 2: Give one control its own CSS

`Style=` is CSS for that control alone, on one line:

```
@Button btnOwn
Parent=c
Canvas.Left=190
Canvas.Top=20
Width=150
Height=40
Content=Its own CSS
Style=background: linear-gradient(135deg, #F59E0B, #EC4899); color: #FFFFFF; border: none; border-radius: 12px
```

In the designer, the **▾** beside the Style box lists ready-made looks (Card, Primary, 3D raised, Outline, Ghost, Glass, Neon and more). Pick one, then edit its CSS in the box below. The look's name is kept as a comment at the front, like `/* Card */`.

## Step 3: Use the style properties

The most common effects are properties of their own, with sliders in the designer:

```
@Button btnProps
Parent=c
Canvas.Left=20
Canvas.Top=90
Width=320
Height=48
Content=Properties: gradient, 3D shadow, hover
Foreground=#FFFFFF
Background=#10B981
GradientTo=#0EA5E9
GradientDirection=Right
CornerRadius=12
Shadow=4
ShadowStyle=3D
HoverBackground=#047857
```

- `Shadow` goes from 0 (none) to 10 (floating well clear). `ShadowStyle` is `Soft` (the default), `3D` (a solid edge below, as if raised) or `Glow` (light all round). `ShadowColour` tints it.
- `Opacity` goes from 100 (solid) to 0 (see-through).
- `GradientTo` fades the `Background` into a second colour; `GradientDirection` is `Down`, `Right`, `Diagonal`, `Up` or `Left`.
- `HoverBackground` and `HoverForeground` are the colours under the pointer.

## Step 4: Change styles while the app runs

`Class` and `Style` are properties like any other, so a script can change them:

```
@Button btnSwap
Parent=c
Canvas.Left=20
Canvas.Top=170
Width=320
Height=40
Content=Click to change my class
Class=pill
OnClick=Swap

@Script Swap
Interpreter=lua
<<LUA
local now = Vml("GetProperty", "btnSwap", "Class")
Vml("SetProperty", "btnSwap", "Class", now == "pill" and "pill big" or "pill")
LUA
```

Each press swaps the button between `pill` and `pill big`.

## Step 5: Check it

Put Steps 1 to 4 together in a form with a `@Window` and `@Canvas`, and open it. You should see a white pill-shaped button that turns pale on hover, an orange-to-pink button, a green-to-blue button sitting on a solid darker edge, and a button whose text grows and shrinks each time you press it. Open the same form as a web page (`vml html Styles.vml --open`) and it looks the same.

## Conclusion

Shared styles keep a whole app consistent, `Style=` handles the one-offs, and the properties cover the everyday effects without writing CSS at all.

Next: [How To Put Your App on the Web](How-To-Put-Your-App-on-the-Web).
