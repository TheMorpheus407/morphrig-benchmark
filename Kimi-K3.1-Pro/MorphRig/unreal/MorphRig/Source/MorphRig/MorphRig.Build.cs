using UnrealBuildTool;

public class MorphRig : ModuleRules
{
    public MorphRig(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core", "CoreUObject", "Engine", "InputCore", "UMG", "Slate", "SlateCore",
            "AnimGraphRuntime", "AnimationCore", "Json", "RHI", "ProceduralMeshComponent"
        });
        PrivateDependencyModuleNames.AddRange(new string[] { "RenderCore" });
        if (Target.bBuildEditor)
        {
            PrivateDependencyModuleNames.AddRange(new string[] { "UnrealEd", "ControlRig", "MovieScene", "MovieSceneTracks" });
        }
    }
}
