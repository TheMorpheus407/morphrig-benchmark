using UnrealBuildTool;
using System.Collections.Generic;
public class MorphRigTarget : TargetRules
{
    public MorphRigTarget(TargetInfo Target) : base(Target)
    {
        Type = TargetType.Game;
        DefaultBuildSettings = BuildSettingsVersion.V7;
        IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
        ExtraModuleNames.Add("MorphRig");
    }
}
