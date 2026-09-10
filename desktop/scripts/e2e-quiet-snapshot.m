// Metadata only: process identities, focus PID/name and visible window owner PID.
// Never request window titles, images, command arguments or process environments.
#import <AppKit/AppKit.h>
#import <ApplicationServices/ApplicationServices.h>
#include <libproc.h>

int main(void) {
  @autoreleasepool {
    NSMutableArray *processes = [NSMutableArray array];
    int count = proc_listallpids(NULL, 0);
    if (count <= 0) { fprintf(stderr, "cannot enumerate processes\n"); return 2; }
    int capacity = count + 1024;
    pid_t *pids = calloc((size_t)capacity, sizeof(pid_t));
    if (!pids) return 2;
    count = proc_listallpids(pids, capacity * sizeof(pid_t));
    if (count <= 0 || count >= capacity) {
      free(pids); fprintf(stderr, "incomplete process list\n"); return 2;
    }
    for (int i = 0; i < count; i++) {
      struct proc_bsdinfo info;
      if (pids[i] <= 0 || proc_pidinfo(pids[i], PROC_PIDTBSDINFO, 0, &info, sizeof(info)) != sizeof(info)) continue;
      [processes addObject:@{
        @"pid": @(info.pbi_pid), @"ppid": @(info.pbi_ppid), @"pgid": @(info.pbi_pgid),
        @"start": [NSString stringWithFormat:@"%llu", (unsigned long long)info.pbi_start_tvsec * 1000000ULL + info.pbi_start_tvusec]
      }];
    }
    free(pids);
    NSRunningApplication *front = NSWorkspace.sharedWorkspace.frontmostApplication;
    id focus = front ? @{@"pid": @(front.processIdentifier), @"name": front.localizedName ?: @"?"} : NSNull.null;
    CFArrayRef raw = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements, kCGNullWindowID);
    if (!raw) { fprintf(stderr, "cannot enumerate windows\n"); return 2; }
    NSMutableArray *windows = [NSMutableArray array];
    for (NSDictionary *window in (__bridge NSArray *)raw) {
      CGRect rect = CGRectZero;
      CGRectMakeWithDictionaryRepresentation((__bridge CFDictionaryRef)window[(id)kCGWindowBounds], &rect);
      [windows addObject:@{
        @"id": window[(id)kCGWindowNumber] ?: @0,
        @"pid": window[(id)kCGWindowOwnerPID] ?: @0,
        @"layer": window[(id)kCGWindowLayer] ?: @0,
        @"owner": window[(id)kCGWindowOwnerName] ?: @"?",
        @"bounds": @[@(rect.origin.x), @(rect.origin.y), @(rect.size.width), @(rect.size.height)]
      }];
    }
    CFRelease(raw);
    NSError *error = nil;
    NSData *json = [NSJSONSerialization dataWithJSONObject:@{@"processes": processes, @"frontmost": focus, @"windows": windows} options:0 error:&error];
    if (!json) { fprintf(stderr, "cannot encode metadata\n"); return 2; }
    fwrite(json.bytes, 1, json.length, stdout);
    putchar('\n');
  }
  return 0;
}
