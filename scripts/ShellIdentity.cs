// Register the actual Start Menu shortcut's AppUserModelID through IPropertyStore.
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
class ShellLinkObject { }

[StructLayout(LayoutKind.Sequential)]
struct PropertyKey {
    public Guid Format;
    public uint Id;
}

[StructLayout(LayoutKind.Explicit, Size = 24)]
struct PropertyVariant {
    [FieldOffset(0)] public ushort Type;
    [FieldOffset(8)] public IntPtr Text;
}

[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IPropertyStore {
    [PreserveSig] int GetCount(out uint count);
    [PreserveSig] int GetAt(uint index, out PropertyKey key);
    [PreserveSig] int GetValue(ref PropertyKey key, out PropertyVariant value);
    [PreserveSig] int SetValue(ref PropertyKey key, ref PropertyVariant value);
    [PreserveSig] int Commit();
}

public static class ShellIdentity {
    public static void SetAppId(string path, string appId) {
        object shell = new ShellLinkObject();
        try {
            IPersistFile file = (IPersistFile)shell;
            file.Load(path, 2);
            IPropertyStore store = (IPropertyStore)shell;
            PropertyKey key = new PropertyKey { Format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), Id = 5 };
            PropertyVariant value = new PropertyVariant { Type = 31, Text = Marshal.StringToCoTaskMemUni(appId) };
            try {
                Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value));
                Marshal.ThrowExceptionForHR(store.Commit());
                file.Save(path, true);
            } finally { Marshal.FreeCoTaskMem(value.Text); }
        } finally { Marshal.FinalReleaseComObject(shell); }
    }
}
