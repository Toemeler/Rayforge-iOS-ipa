/*
 * gdkiosmain.m — UIKit shell for the GDK iOS backend.
 *
 * Provides:
 *  - GdkIOSView: fullscreen UIView translating UIKit input into GDK
 *    events with desktop mouse+keyboard semantics:
 *      * trackpad/mouse hover  -> motion events   (UIHoverGestureRecognizer)
 *      * touches / clicks      -> button 1 press/motion/release
 *      * two-finger / wheel    -> smooth scroll   (UIPanGestureRecognizer,
 *                                 scroll-typed input only)
 *      * hardware keyboard     -> key press/release with full modifiers
 *  - The application bootstrap gdk_ios_main(): runs UIApplicationMain,
 *    creates the window + root view, then pumps the GLib main context
 *    from a CADisplayLink so GTK runs on the UIKit main thread.
 *
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#import <UIKit/UIKit.h>
#import <QuartzCore/QuartzCore.h>

#include <gdk/gdk.h>
#include <gdk/gdkkeysyms.h>
#include "gdkiosprivate.h"
#include "gdkios.h"

/* ------------------------------------------------------------ shell state */

static UIWindow *shell_window = nil;
static UIView *shell_view = nil;
static gboolean shell_ready = FALSE;

static double pointer_x = 0.0;
static double pointer_y = 0.0;
static GdkModifierType key_modifiers = 0;
static GdkModifierType button_modifiers = 0;
static GdkIOSSurface *pointer_surface = NULL; /* weak */

static GdkIOSMainFunc user_main_func = NULL;
static gpointer user_main_data = NULL;

gboolean
gdk_ios_shell_is_ready (void)
{
  return shell_ready;
}

gpointer
gdk_ios_shell_get_root_layer (void)
{
  return (__bridge gpointer) shell_view.layer;
}

double
gdk_ios_shell_get_scale (void)
{
  if (shell_window != nil)
    return shell_window.screen.scale;
  return [UIScreen mainScreen].scale;
}

void
gdk_ios_shell_get_bounds (int *width, int *height)
{
  CGRect b = shell_view != nil ? shell_view.bounds
                               : [UIScreen mainScreen].bounds;
  if (width) *width = (int) b.size.width;
  if (height) *height = (int) b.size.height;
}

void
gdk_ios_shell_get_pointer_position (double *x, double *y,
                                    GdkModifierType *mask)
{
  if (x) *x = pointer_x;
  if (y) *y = pointer_y;
  if (mask) *mask = key_modifiers | button_modifiers;
}

/* --------------------------------------------------------- event helpers */

static guint32
event_time_now (void)
{
  return (guint32) (g_get_monotonic_time () / 1000);
}

static GdkIOSDisplay *
get_display (void)
{
  return gdk_ios_display_get_instance ();
}

static void
update_pointer_surface (GdkIOSDisplay *display,
                        GdkIOSSurface *new_surface,
                        double lx, double ly,
                        guint32 time)
{
  if (new_surface == pointer_surface)
    return;

  GdkModifierType state = key_modifiers | button_modifiers;

  if (pointer_surface != NULL)
    gdk_ios_display_deliver_event (display,
      gdk_crossing_event_new (GDK_LEAVE_NOTIFY,
                              GDK_SURFACE (pointer_surface),
                              display->core_pointer,
                              time, state, lx, ly,
                              GDK_CROSSING_NORMAL,
                              GDK_NOTIFY_NONLINEAR));
  pointer_surface = new_surface;
  if (new_surface != NULL)
    gdk_ios_display_deliver_event (display,
      gdk_crossing_event_new (GDK_ENTER_NOTIFY,
                              GDK_SURFACE (new_surface),
                              display->core_pointer,
                              time, state, lx, ly,
                              GDK_CROSSING_NORMAL,
                              GDK_NOTIFY_NONLINEAR));
}

static void
deliver_motion (double root_x, double root_y)
{
  GdkIOSDisplay *display = get_display ();
  if (display == NULL)
    return;

  pointer_x = root_x;
  pointer_y = root_y;

  double lx = 0, ly = 0;
  GdkIOSSurface *target = gdk_ios_display_surface_at (display,
                                                      root_x, root_y,
                                                      &lx, &ly);
  guint32 time = event_time_now ();
  update_pointer_surface (display, target, lx, ly, time);
  if (target == NULL)
    return;

  gdk_ios_display_deliver_event (display,
    gdk_motion_event_new (GDK_SURFACE (target),
                          display->core_pointer,
                          NULL, time,
                          key_modifiers | button_modifiers,
                          lx, ly, NULL));
}

static void
deliver_button (GdkEventType type, guint button,
                double root_x, double root_y)
{
  GdkIOSDisplay *display = get_display ();
  if (display == NULL)
    return;

  pointer_x = root_x;
  pointer_y = root_y;

  double lx = 0, ly = 0;
  GdkIOSSurface *target = gdk_ios_display_surface_at (display,
                                                      root_x, root_y,
                                                      &lx, &ly);
  guint32 time = event_time_now ();
  update_pointer_surface (display, target, lx, ly, time);
  if (target == NULL)
    return;

  GdkModifierType button_mask =
    (GdkModifierType) (GDK_BUTTON1_MASK << (button - 1));
  if (type == GDK_BUTTON_PRESS)
    button_modifiers |= button_mask;

  gdk_ios_display_deliver_event (display,
    gdk_button_event_new (type,
                          GDK_SURFACE (target),
                          display->core_pointer,
                          NULL, time,
                          key_modifiers | button_modifiers,
                          button, lx, ly, NULL));

  if (type == GDK_BUTTON_RELEASE)
    button_modifiers &= ~button_mask;
}

static void
deliver_scroll (double dx, double dy, gboolean is_stop)
{
  GdkIOSDisplay *display = get_display ();
  if (display == NULL)
    return;

  double lx = 0, ly = 0;
  GdkIOSSurface *target = gdk_ios_display_surface_at (display,
                                                      pointer_x, pointer_y,
                                                      &lx, &ly);
  if (target == NULL)
    return;

  gdk_ios_display_deliver_event (display,
    gdk_scroll_event_new (GDK_SURFACE (target),
                          display->core_pointer,
                          NULL, event_time_now (),
                          key_modifiers | button_modifiers,
                          dx, dy, is_stop,
                          GDK_SCROLL_UNIT_SURFACE,
                          GDK_SCROLL_RELATIVE_DIRECTION_UNKNOWN));
}

/* -------------------------------------------------------- key translation */

static GdkModifierType
modifiers_from_flags (UIKeyModifierFlags flags)
{
  GdkModifierType state = 0;
  if (flags & UIKeyModifierShift)
    state |= GDK_SHIFT_MASK;
  if (flags & UIKeyModifierControl)
    state |= GDK_CONTROL_MASK;
  if (flags & UIKeyModifierAlternate)
    state |= GDK_ALT_MASK;
  if (flags & UIKeyModifierCommand)
    state |= GDK_META_MASK;
  if (flags & UIKeyModifierAlphaShift)
    state |= GDK_LOCK_MASK;
  return state;
}

static guint
keyval_from_uikey (UIKey *key)
{
  switch (key.keyCode)
    {
    case UIKeyboardHIDUsageKeyboardReturnOrEnter: return GDK_KEY_Return;
    case UIKeyboardHIDUsageKeypadEnter:           return GDK_KEY_KP_Enter;
    case UIKeyboardHIDUsageKeyboardEscape:        return GDK_KEY_Escape;
    case UIKeyboardHIDUsageKeyboardDeleteOrBackspace: return GDK_KEY_BackSpace;
    case UIKeyboardHIDUsageKeyboardDeleteForward: return GDK_KEY_Delete;
    case UIKeyboardHIDUsageKeyboardTab:           return GDK_KEY_Tab;
    case UIKeyboardHIDUsageKeyboardUpArrow:       return GDK_KEY_Up;
    case UIKeyboardHIDUsageKeyboardDownArrow:     return GDK_KEY_Down;
    case UIKeyboardHIDUsageKeyboardLeftArrow:     return GDK_KEY_Left;
    case UIKeyboardHIDUsageKeyboardRightArrow:    return GDK_KEY_Right;
    case UIKeyboardHIDUsageKeyboardHome:          return GDK_KEY_Home;
    case UIKeyboardHIDUsageKeyboardEnd:           return GDK_KEY_End;
    case UIKeyboardHIDUsageKeyboardPageUp:        return GDK_KEY_Page_Up;
    case UIKeyboardHIDUsageKeyboardPageDown:      return GDK_KEY_Page_Down;
    case UIKeyboardHIDUsageKeyboardInsert:        return GDK_KEY_Insert;
    case UIKeyboardHIDUsageKeyboardLeftShift:     return GDK_KEY_Shift_L;
    case UIKeyboardHIDUsageKeyboardRightShift:    return GDK_KEY_Shift_R;
    case UIKeyboardHIDUsageKeyboardLeftControl:   return GDK_KEY_Control_L;
    case UIKeyboardHIDUsageKeyboardRightControl:  return GDK_KEY_Control_R;
    case UIKeyboardHIDUsageKeyboardLeftAlt:       return GDK_KEY_Alt_L;
    case UIKeyboardHIDUsageKeyboardRightAlt:      return GDK_KEY_Alt_R;
    case UIKeyboardHIDUsageKeyboardLeftGUI:       return GDK_KEY_Meta_L;
    case UIKeyboardHIDUsageKeyboardRightGUI:      return GDK_KEY_Meta_R;
    case UIKeyboardHIDUsageKeyboardCapsLock:      return GDK_KEY_Caps_Lock;
    case UIKeyboardHIDUsageKeyboardF1:  return GDK_KEY_F1;
    case UIKeyboardHIDUsageKeyboardF2:  return GDK_KEY_F2;
    case UIKeyboardHIDUsageKeyboardF3:  return GDK_KEY_F3;
    case UIKeyboardHIDUsageKeyboardF4:  return GDK_KEY_F4;
    case UIKeyboardHIDUsageKeyboardF5:  return GDK_KEY_F5;
    case UIKeyboardHIDUsageKeyboardF6:  return GDK_KEY_F6;
    case UIKeyboardHIDUsageKeyboardF7:  return GDK_KEY_F7;
    case UIKeyboardHIDUsageKeyboardF8:  return GDK_KEY_F8;
    case UIKeyboardHIDUsageKeyboardF9:  return GDK_KEY_F9;
    case UIKeyboardHIDUsageKeyboardF10: return GDK_KEY_F10;
    case UIKeyboardHIDUsageKeyboardF11: return GDK_KEY_F11;
    case UIKeyboardHIDUsageKeyboardF12: return GDK_KEY_F12;
    default:
      break;
    }

  NSString *chars = key.charactersIgnoringModifiers;
  if (chars.length > 0)
    {
      gunichar uc = [chars characterAtIndex:0];
      guint keyval = gdk_unicode_to_keyval (uc);
      if (keyval != (uc | 0x01000000) || uc >= 0x20)
        return keyval;
    }
  return GDK_KEY_VoidSymbol;
}

static void
deliver_key (GdkEventType type, UIKey *key)
{
  GdkIOSDisplay *display = get_display ();
  if (display == NULL || display->toplevels == NULL)
    return;

  GdkSurface *target = GDK_SURFACE (display->toplevels->data);
  guint keyval = keyval_from_uikey (key);
  if (keyval == GDK_KEY_VoidSymbol)
    return;

  GdkModifierType state = modifiers_from_flags (key.modifierFlags);
  key_modifiers = state;

  gboolean is_modifier =
    (keyval >= GDK_KEY_Shift_L && keyval <= GDK_KEY_Hyper_R) ||
    keyval == GDK_KEY_Caps_Lock;

  GdkTranslatedKey translated = {
    .keyval = keyval,
    .consumed = 0,
    .layout = 0,
    .level = 0,
  };

  gdk_ios_display_deliver_event (display,
    gdk_key_event_new (type, target,
                       display->core_keyboard,
                       event_time_now (),
                       keyval, /* identity keymap: keycode == keyval */
                       state, is_modifier,
                       &translated, &translated, NULL));
}

/* ---------------------------------------------------------------- UIView */

@interface GdkIOSView : UIView <UIPointerInteractionDelegate>
@end

@implementation GdkIOSView

- (instancetype)initWithFrame:(CGRect)frame
{
  self = [super initWithFrame:frame];
  if (self)
    {
      self.multipleTouchEnabled = YES;
      self.backgroundColor = [UIColor blackColor];

      UIHoverGestureRecognizer *hover =
        [[UIHoverGestureRecognizer alloc] initWithTarget:self
                                                  action:@selector(onHover:)];
      [self addGestureRecognizer:hover];

      UIPanGestureRecognizer *scroll =
        [[UIPanGestureRecognizer alloc] initWithTarget:self
                                                action:@selector(onScroll:)];
      scroll.allowedScrollTypesMask = UIScrollTypeMaskAll;
      scroll.allowedTouchTypes = @[]; /* scroll-typed input only, not touches */
      scroll.maximumNumberOfTouches = 0;
      [self addGestureRecognizer:scroll];

      [self addInteraction:
        [[UIPointerInteraction alloc] initWithDelegate:self]];
    }
  return self;
}

- (BOOL)canBecomeFirstResponder
{
  return YES;
}

- (void)onHover:(UIHoverGestureRecognizer *)recognizer
{
  CGPoint p = [recognizer locationInView:self];
  deliver_motion (p.x, p.y);
}

- (void)onScroll:(UIPanGestureRecognizer *)recognizer
{
  CGPoint t = [recognizer translationInView:self];
  [recognizer setTranslation:CGPointZero inView:self];
  gboolean is_stop = (recognizer.state == UIGestureRecognizerStateEnded ||
                      recognizer.state == UIGestureRecognizerStateCancelled);
  /* GDK scroll deltas: positive = content moves up/left. */
  deliver_scroll (-t.x, -t.y, is_stop);
}

- (void)touchesBegan:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event
{
  UITouch *touch = [touches anyObject];
  CGPoint p = [touch locationInView:self];
  deliver_motion (p.x, p.y);
  deliver_button (GDK_BUTTON_PRESS,
                  (touch.type == UITouchTypeIndirectPointer &&
                   (event.buttonMask & UIEventButtonMaskSecondary)) ? 3 : 1,
                  p.x, p.y);
}

- (void)touchesMoved:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event
{
  UITouch *touch = [touches anyObject];
  CGPoint p = [touch locationInView:self];
  deliver_motion (p.x, p.y);
}

- (void)touchesEnded:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event
{
  UITouch *touch = [touches anyObject];
  CGPoint p = [touch locationInView:self];
  deliver_button (GDK_BUTTON_RELEASE,
                  (touch.type == UITouchTypeIndirectPointer &&
                   (event.buttonMask & UIEventButtonMaskSecondary)) ? 3 : 1,
                  p.x, p.y);
}

- (void)touchesCancelled:(NSSet<UITouch *> *)touches withEvent:(UIEvent *)event
{
  [self touchesEnded:touches withEvent:event];
}

- (void)pressesBegan:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event
{
  BOOL handled = NO;
  for (UIPress *press in presses)
    if (press.key != nil)
      {
        deliver_key (GDK_KEY_PRESS, press.key);
        handled = YES;
      }
  if (!handled)
    [super pressesBegan:presses withEvent:event];
}

- (void)pressesEnded:(NSSet<UIPress *> *)presses withEvent:(UIPressesEvent *)event
{
  BOOL handled = NO;
  for (UIPress *press in presses)
    if (press.key != nil)
      {
        deliver_key (GDK_KEY_RELEASE, press.key);
        handled = YES;
      }
  if (!handled)
    [super pressesEnded:presses withEvent:event];
}

/* Hide the system pointer circle; GTK draws its own UI affordances. */
- (UIPointerStyle *)pointerInteraction:(UIPointerInteraction *)interaction
                        styleForRegion:(UIPointerRegion *)region
{
  return nil; /* default system pointer */
}

@end

/* --------------------------------------------------------- app bootstrap */

/* Root view controller. iOS drives interface orientation from the root
 * VC's supportedInterfaceOrientations (intersected with the Info.plist
 * keys); a bare UIViewController reports "all", so the app never locked
 * to the landscape the Info.plist requests. Force landscape here and log
 * the orientation actually granted so we can see what the device did. */
@interface GdkIOSViewController : UIViewController
@end

@implementation GdkIOSViewController

- (UIInterfaceOrientationMask)supportedInterfaceOrientations
{
  return UIInterfaceOrientationMaskLandscape;
}

- (BOOL)shouldAutorotate
{
  return YES;
}

- (BOOL)prefersStatusBarHidden
{
  return YES;
}

- (BOOL)prefersHomeIndicatorAutoHidden
{
  return YES;
}

- (void)viewDidLayoutSubviews
{
  [super viewDidLayoutSubviews];
  CGRect s = [UIScreen mainScreen].bounds;
  g_message ("gdk-ios: VC layout view=%.0fx%.0f screen=%.0fx%.0f",
             (double) self.view.bounds.size.width,
             (double) self.view.bounds.size.height,
             (double) s.size.width, (double) s.size.height);
}

@end

@interface GdkIOSAppDelegate : UIResponder <UIApplicationDelegate>
@property (strong, nonatomic) UIWindow *window;
@property (strong, nonatomic) CADisplayLink *displayLink;
@end

@implementation GdkIOSAppDelegate

- (void)pumpGLib:(CADisplayLink *)link
{
  static unsigned long frames = 0;
  static unsigned long iterations = 0;
  GMainContext *context = g_main_context_default ();
  while (g_main_context_pending (context))
    {
      g_main_context_iteration (context, FALSE);
      iterations++;
    }
  if ((++frames % 120) == 0)
    g_message ("gdk-ios: pump alive frame=%lu total_iterations=%lu",
               frames, iterations);
}

- (BOOL)application:(UIApplication *)application
    didFinishLaunchingWithOptions:(NSDictionary *)launchOptions
{
  self.window = [[UIWindow alloc] initWithFrame:[UIScreen mainScreen].bounds];
  GdkIOSViewController *vc = [[GdkIOSViewController alloc] init];
  GdkIOSView *view = [[GdkIOSView alloc] initWithFrame:self.window.bounds];
  view.autoresizingMask =
    UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  vc.view = view;
  self.window.rootViewController = vc;
  [self.window makeKeyAndVisible];
  [view becomeFirstResponder];

  shell_window = self.window;
  shell_view = view;
  shell_ready = TRUE;

  g_message ("gdk-ios: shell ready window=%.0fx%.0f view=%.0fx%.0f scale=%.2f",
             (double) self.window.bounds.size.width,
             (double) self.window.bounds.size.height,
             (double) view.bounds.size.width,
             (double) view.bounds.size.height,
             (double) shell_window.screen.scale);

  /* Pump the GLib default main context at display refresh rate; GTK and
   * the application run entirely on the UIKit main thread. */
  self.displayLink = [CADisplayLink displayLinkWithTarget:self
                                                 selector:@selector(pumpGLib:)];
  [self.displayLink addToRunLoop:[NSRunLoop mainRunLoop]
                         forMode:NSRunLoopCommonModes];

  /* Enter the application's real main after UIKit is fully up. */
  dispatch_async (dispatch_get_main_queue (), ^{
    g_message ("gdk-ios: entering user main");
    if (user_main_func != NULL)
      user_main_func (user_main_data);
    g_message ("gdk-ios: user main returned");
  });

  return YES;
}

@end

/* Point the GLib/GTK/fontconfig stack at the app bundle and sandbox.
 * iOS apps launch with an empty environment: without this, GSettings
 * finds no compiled schemas, fontconfig finds no configuration (and
 * pango therefore no fonts), and caches would target invalid paths. */
static void
gdk_ios_bootstrap_environment (void)
{
  NSString *res = [[NSBundle mainBundle] resourcePath];
  NSString *caches = NSSearchPathForDirectoriesInDomains (
      NSCachesDirectory, NSUserDomainMask, YES).firstObject;
  NSString *share = [res stringByAppendingPathComponent:@"share"];

  g_setenv ("XDG_DATA_DIRS", share.UTF8String, FALSE);
  g_setenv ("GSETTINGS_SCHEMA_DIR",
            [share stringByAppendingPathComponent:@"glib-2.0/schemas"].UTF8String,
            FALSE);
  g_setenv ("XDG_CACHE_HOME", caches.UTF8String, FALSE);
  g_setenv ("XDG_CONFIG_HOME",
            [caches stringByAppendingPathComponent:@"config"].UTF8String,
            FALSE);
  g_setenv ("XDG_DATA_HOME",
            [caches stringByAppendingPathComponent:@"data"].UTF8String,
            FALSE);

  NSString *fontsconf =
    [res stringByAppendingPathComponent:@"etc/fonts/fonts.conf"];
  if ([[NSFileManager defaultManager] fileExistsAtPath:fontsconf])
    g_setenv ("FONTCONFIG_FILE", fontsconf.UTF8String, FALSE);

  g_message ("gdk-ios: bundle resources at %s", res.UTF8String);
}

/* Replacement for g_application_run() on iOS. g_application_run()'s
 * blocking GMainLoop would stall the UIKit run loop, so instead we
 * register + activate the application and let the CADisplayLink pump
 * (which drives the GLib default context) deliver everything after
 * that. GtkApplication/AdwApplication perform their real init (gtk_init,
 * adw_init, stylesheet, window tracking) in ::startup, which
 * g_application_register() emits, so full Application semantics are
 * preserved. A reference is kept so the application object stays alive
 * for the lifetime of the process. */
int
gdk_ios_application_run (GApplication *app)
{
  GError *error = NULL;

  g_return_val_if_fail (G_IS_APPLICATION (app), 1);

  if (!g_application_register (app, NULL, &error))
    {
      g_critical ("gdk-ios: failed to register application: %s",
                  error != NULL ? error->message : "unknown error");
      g_clear_error (&error);
      return 1;
    }

  g_application_activate (app);
  g_object_ref (app);

  return 0;
}

int
gdk_ios_main (int argc, char **argv,
              GdkIOSMainFunc main_func, gpointer user_data)
{
  user_main_func = main_func;
  user_main_data = user_data;

  gdk_ios_bootstrap_environment ();

  /* The GL renderer is unavailable; skip GSK probing noise. */
  g_setenv ("GSK_RENDERER", "cairo", FALSE);
  g_setenv ("GDK_BACKEND", "ios", FALSE);

  @autoreleasepool
    {
      return UIApplicationMain (argc, argv, nil,
                                NSStringFromClass ([GdkIOSAppDelegate class]));
    }
}
