using UnrealBuildTool;
public class MorphRig : ModuleRules
{
    public MorphRig(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "Json", "JsonUtilities", "AnimationCore", "AnimGraphRuntime", "Slate", "SlateCore", "RHI", "RenderCore" });
    }
}
